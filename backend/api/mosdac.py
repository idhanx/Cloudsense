"""
CloudSense — MOSDAC Download Routes
SSE-streamed download from MOSDAC API with strict time filtering.
"""

import os
import json
import glob
import uuid
import subprocess
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.config import settings
from core.security import get_optional_user_id, rate_limiter  # ✅ FIXED: was get_optional_user
from core.database import create_analysis, update_analysis_status, save_analysis_results
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mosdac", tags=["mosdac"])


class MOSDACDownloadRequest(BaseModel):
    username: str
    password: str
    hours_back: float = Field(default=1, ge=0.5, le=12, description="Hours back (0.5–12)")


def _sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _parse_filename_time(filename: str):
    """Extract datetime from MOSDAC filename like 3RIMG_24MAR2026_1245_..."""
    try:
        parts = filename.split("_")
        return datetime.strptime(f"{parts[1]}_{parts[2]}", "%d%b%Y_%H%M")
    except Exception:
        return None


@router.post("/download")
async def download_mosdac_data(
    request: MOSDACDownloadRequest,
    req: Request,
    user: Optional[str] = Depends(get_optional_user_id),  # ✅ FIXED: was get_optional_user
):
    """Download INSAT-3DR data from MOSDAC with strict time filtering + run inference."""
    rate_limiter.check(req.client.host)

    def stream_generator():
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=request.hours_back)
            # INSAT-3DR produces one file every 30 minutes
            # hours_back=0.5 → 1 file, hours_back=1 → 2 files, etc.
            max_files = max(1, round(request.hours_back * 2))

            yield _sse_event("progress", {"step": "config", "message": "Preparing download configuration..."})

            # Build config for mdapi
            config = {
                "user_credentials": {"username": request.username, "password": request.password},
                "search_parameters": {
                    "datasetId": "3RIMG_L1C_ASIA_MER",
                    "startTime": start_time.strftime("%Y-%m-%d"),
                    "endTime": end_time.strftime("%Y-%m-%d"),
                    "count": str(max_files),
                    "boundingBox": "",
                    "gId": "",
                },
                "download_settings": {
                    "download_path": settings.MOSDAC_DATA_DIR,
                    "organize_by_date": False,
                    "skip_user_prompt": True,
                    "generate_error_log": False,
                    "error_log_path": "",
                },
            }

            config_path = os.path.join(settings.BASE_DIR, "config.json")
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            yield _sse_event("progress", {"step": "connect", "message": "Connecting to MOSDAC API..."})

            # Run mdapi.py
            mdapi_path = os.path.join(settings.BASE_DIR, "mosdac_engine", "mdapi.py")
            if not os.path.exists(mdapi_path):
                yield _sse_event("error", {"message": "mdapi.py not found"})
                return

            import sys
            python_exe = sys.executable  # Use same Python as the running process
            process = subprocess.Popen(
                [python_exe, "-u", mdapi_path],
                cwd=settings.BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            noise_patterns = ["%|", "resource_tracker", "UserWarning", "warnings.warn"]
            for line in iter(process.stdout.readline, ""):
                line = line.strip()
                if not line or any(p in line for p in noise_patterns):
                    continue
                if "[ERROR]" in line:
                    yield _sse_event("progress", {"step": "download", "message": f"⚠ {line}"})
                elif "[SKIP]" in line:
                    yield _sse_event("progress", {"step": "download", "message": f"⏭ {line}"})
                elif "Found" in line and "files" in line:
                    yield _sse_event("progress", {"step": "search", "message": f"🔍 {line}"})
                elif "Downloading" in line or "RETRY" in line:
                    yield _sse_event("progress", {"step": "download", "message": f"📥 {line}"})
                elif "Logged in" in line:
                    yield _sse_event("progress", {"step": "auth", "message": f"✓ {line}"})
                elif "Download complete" in line:
                    yield _sse_event("progress", {"step": "download_done", "message": f"✓ {line}"})
                else:
                    yield _sse_event("progress", {"step": "download", "message": line})

            process.stdout.close()
            stderr_output = process.stderr.read()
            process.stderr.close()
            return_code = process.wait(timeout=600)

            if return_code != 0:
                error_lines = [l for l in stderr_output.splitlines() if l.strip() and not any(p in l for p in noise_patterns)]
                error_msg = "\n".join(error_lines[-5:]) if error_lines else f"Process exited with code {return_code}"
                logger.error(f"MOSDAC Error: {error_msg}")
                yield _sse_event("error", {"message": f"Download failed: {error_msg}"})
                return

            # ── TIME FILTERING ──
            # Find ALL H5 files in the data dir within the requested time window
            # (includes already-downloaded files — skip only means "don't re-download", not "don't process")
            all_h5 = set(glob.glob(os.path.join(settings.MOSDAC_DATA_DIR, "**", "*.h5"), recursive=True))
            all_h5.update(glob.glob(os.path.join(settings.MOSDAC_DATA_DIR, "*.h5")))

            h5_files = []
            for path in sorted(all_h5):
                fname = os.path.basename(path)
                file_time = _parse_filename_time(fname)
                if file_time and start_time <= file_time <= end_time:
                    h5_files.append(path)

            if not h5_files:
                yield _sse_event("done", {
                    "status": "no_data",
                    "message": "No data available for the selected time range",
                    "files_downloaded": 0,
                    "results": [],
                })
                return

            # Run inference
            yield _sse_event("progress", {
                "step": "inference",
                "message": f"Running U-Net inference on {len(h5_files)} file(s)...",
            })

            from api.upload import get_inference_pipeline
            pipeline = get_inference_pipeline()
            results = []

            for i, h5_path in enumerate(h5_files, 1):
                fname = os.path.basename(h5_path)
                yield _sse_event("progress", {
                    "step": "inference",
                    "message": f"🧠 Processing [{i}/{len(h5_files)}]: {fname}...",
                })

                analysis_id = str(uuid.uuid4())
                create_analysis(
                    analysis_id=analysis_id,
                    filename=fname,
                    file_path=h5_path,
                    source="mosdac_download",
                    user_id=user if user else None,  # ✅ FIXED: user is now a str, not dict
                )

                result = pipeline.process_file(h5_path, settings.OUTPUT_DIR, analysis_id)

                if result["success"]:
                    update_analysis_status(analysis_id, "complete")
                    save_analysis_results(analysis_id, result)
                    file_result = {
                        "analysis_id": analysis_id,
                        "file": fname,
                        "tcc_pixels": result.get("tcc_pixels", 0),
                        "tcc_count": result.get("tcc_count", 0),
                        "total_area_km2": result.get("total_area_km2", 0),
                        "detections": result.get("detections", []),
                        "outputs": {
                            "satellite_png": f"/api/download/{analysis_id}/satellite.png",
                            "mask_npy": f"/api/download/{analysis_id}/mask.npy",
                            "mask_png": f"/api/download/{analysis_id}/mask.png",
                            "overlay_png": f"/api/download/{analysis_id}/overlay.png",
                            "netcdf": f"/api/download/{analysis_id}/output.nc",
                        },
                    }
                    results.append(file_result)
                    tcc_count = result.get("tcc_count", 0)
                    yield _sse_event("progress", {
                        "step": "inference",
                        "message": f"✓ {fname} — {tcc_count} TCCs detected",
                    })
                else:
                    update_analysis_status(analysis_id, "failed")
                    yield _sse_event("progress", {
                        "step": "inference",
                        "message": f"⚠ Failed to process {fname}",
                    })

            yield _sse_event("done", {
                "status": "success",
                "message": f"Downloaded and processed {len(h5_files)} files",
                "files_downloaded": len(h5_files),
                "results": results,
            })

        except Exception as e:
            logger.error(f"MOSDAC stream error: {e}")
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )