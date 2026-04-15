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
