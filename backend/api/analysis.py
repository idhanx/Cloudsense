"""
CloudSense — Analysis & Dashboard Routes
No auth required — data is public.
"""

import json
import logging
from fastapi import APIRouter

from core.database import get_recent_analyses, get_dashboard_stats, get_all_recent_clusters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/analyses/recent")
async def list_recent_analyses(limit: int = 10):
    analyses = get_recent_analyses(limit)
    for a in analyses:
        if a.get("results"):
            try:
                if isinstance(a["results"], str):
                    a["results"] = json.loads(a["results"])
            except json.JSONDecodeError:
                a["results"] = {}
    return analyses


@router.get("/dashboard/stats")
async def dashboard_stats():
    return get_dashboard_stats()


@router.get("/analysis/clusters")
async def analysis_clusters(limit: int = 50):
    return get_all_recent_clusters(limit)
