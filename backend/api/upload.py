"""
CloudSense — Upload & Inference Routes
File upload, inference execution, and output download.
Auth via Neon Auth (x-user-id header).
"""

import os
import shutil
import uuid
import asyncio
import logging
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends, Request
from fastapi.responses import FileResponse
from typing import Optional

from core.config import settings
from core.security import get_user_id, get_optional_user_id, rate_limiter
from core.database import create_analysis, update_analysis_status, save_analysis_results

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["upload"])

# ── Lazy-loaded inference pipeline ──
_inference_pipeline = None

def get_inference_pipeline():
    global _inference_pipeline
    if _inference_pipeline is None:
        from inference_engine import InferencePipeline
        _inference_pipeline = InferencePipeline(model_path=settings.MODEL_PATH)
        logger.info("Inference pipeline loaded")
    return _inference_pipeline


def _run_inference_sync(file_path: str, file_ext: str, output_dir: str, analysis_id: str):
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
    pipeline = get_inference_pipeline()
    if file_ext in IMAGE_EXTENSIONS:
        return pipeline.process_image(file_path, output_dir, analysis_id)
    else:
        return pipeline.process_file(file_path, output_dir, analysis_id)


# ── Upload Endpoint (Neon Auth Required) ──

@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id),
):
    """Upload H5 or image file, run inference, return results. Requires Neon Auth."""
    rate_limiter.check(request.client.host)

    try:
        # Validate extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Only {settings.ALLOWED_EXTENSIONS} files allowed. Got: {file_ext}",
            )

        # Validate size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(status_code=413, detail=f"File too large. Max: {settings.MAX_UPLOAD_SIZE_MB}MB")

        # Save file
        analysis_id = str(uuid.uuid4())
        storage_filename = f"{analysis_id}{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, storage_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"📤 File uploaded: {file.filename} -> {analysis_id}")

        # Create DB record
        create_analysis(
            analysis_id=analysis_id,
            filename=file.filename,
            file_path=file_path,
            source="manual_upload",
            user_id=user_id,
        )

        # Run inference in thread pool
        logger.info(f"🧠 Starting inference for {analysis_id}...")
        IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
        result = await asyncio.to_thread(
            _run_inference_sync, file_path, file_ext, settings.OUTPUT_DIR, analysis_id
        )

        if result["success"]:
            update_analysis_status(analysis_id, "complete")
            save_analysis_results(analysis_id, result)
            logger.info(f"✅ Inference complete: {analysis_id} — {result.get('tcc_count', 0)} TCCs")

            outputs = {
                "satellite_png": f"/api/download/{analysis_id}/satellite.png",
                "mask_npy": f"/api/download/{analysis_id}/mask.npy",
                "mask_png": f"/api/download/{analysis_id}/mask.png",
                "overlay_png": f"/api/download/{analysis_id}/overlay.png",
                "netcdf": f"/api/download/{analysis_id}/output.nc" if file_ext not in IMAGE_EXTENSIONS else None,
            }
            return {
                "analysis_id": analysis_id,
                "status": "complete",
                "message": f"Processed {file.filename}",
                "input_type": "image" if file_ext in IMAGE_EXTENSIONS else "h5",
                "outputs": outputs,
                "tcc_pixels": result.get("tcc_pixels", 0),
                "tcc_count": result.get("tcc_count", 0),
                "total_area_km2": result.get("total_area_km2", 0),
                "detections": result.get("detections", []),
            }
        else:
            update_analysis_status(analysis_id, "failed")
            logger.error(f"❌ Inference failed: {result.get('error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Inference failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Download Outputs (NO AUTH REQUIRED) ──

ALLOWED_OUTPUT_FILES = {"satellite.png", "mask.npy", "mask.png", "overlay.png", "output.nc"}
MEDIA_TYPES = {
    "satellite.png": "image/png",
    "mask.npy": "application/octet-stream",
    "mask.png": "image/png",
    "overlay.png": "image/png",
    "output.nc": "application/x-netcdf",
}

@router.get("/download/{analysis_id}/{filename}")
async def download_output(
    analysis_id: str,
    filename: str,
):
    """Download output files (public)."""
    if filename not in ALLOWED_OUTPUT_FILES:
        raise HTTPException(status_code=400, detail=f"Invalid file. Options: {ALLOWED_OUTPUT_FILES}")

    file_path = os.path.join(settings.OUTPUT_DIR, analysis_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type=MEDIA_TYPES.get(filename, "application/octet-stream"),
        filename=f"{analysis_id}_{filename}",
    )
