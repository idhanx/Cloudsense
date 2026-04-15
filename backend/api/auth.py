"""
CloudSense — Auth Routes (Neon Auth)
No login/signup endpoints — authentication is handled by Neon Auth on the frontend.
Only provides a user verification endpoint.
"""

import logging
from fastapi import APIRouter, Depends

from core.security import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/verify")
async def verify_user(user_id: str = Depends(get_user_id)):
    """Verify that the user is authenticated via Neon Auth."""
    return {"authenticated": True, "user_id": user_id}
