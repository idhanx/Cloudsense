"""
CloudSense — Export Routes
No auth required — export listing is public.
"""

import os
import logging
from fastapi import APIRouter

from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["exports"])


@router.get("/exports")
async def list_exports():
    exports = []
    if os.path.exists(settings.OUTPUT_DIR):
        for analysis_id in os.listdir(settings.OUTPUT_DIR):
            analysis_dir = os.path.join(settings.OUTPUT_DIR, analysis_id)
            if os.path.isdir(analysis_dir):
                files = os.listdir(analysis_dir)
                exports.append({
                    "analysis_id": analysis_id,
                    "files": files,
                    "download_urls": {
                        "satellite_png": f"/api/download/{analysis_id}/satellite.png" if "satellite.png" in files else None,
                        "mask_npy": f"/api/download/{analysis_id}/mask.npy" if "mask.npy" in files else None,
                        "mask_png": f"/api/download/{analysis_id}/mask.png" if "mask.png" in files else None,
                        "overlay_png": f"/api/download/{analysis_id}/overlay.png" if "overlay.png" in files else None,
                        "netcdf": f"/api/download/{analysis_id}/output.nc" if "output.nc" in files else None,
                    },
                })
    return exports


from fastapi.responses import FileResponse
from fastapi import HTTPException
import re


@router.get("/download/{analysis_id}/output.nc")
async def download_netcdf(analysis_id: str):
    """
    Download NetCDF file for a completed analysis.

    Args:
        analysis_id: Analysis UUID

    Returns:
        FileResponse with Content-Type: application/x-netcdf

    Raises:
        HTTPException 400 if analysis_id is not a valid UUID
        HTTPException 404 if file not found
    """
    # Validate analysis_id is a UUID — prevents path traversal
    if not re.fullmatch(r"[0-9a-f\-]{36}", analysis_id):
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    netcdf_path = os.path.join(settings.OUTPUT_DIR, analysis_id, "output.nc")

    # Belt-and-suspenders: confirm resolved path stays inside OUTPUT_DIR
    if not os.path.realpath(netcdf_path).startswith(os.path.realpath(settings.OUTPUT_DIR)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not os.path.exists(netcdf_path):
        raise HTTPException(
            status_code=404,
            detail=f"NetCDF file not found for analysis {analysis_id}"
        )

    return FileResponse(
        netcdf_path,
        media_type="application/x-netcdf",
        filename=f"{analysis_id}_output.nc"
    )
