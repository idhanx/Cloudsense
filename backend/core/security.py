"""
CloudSense — Security Utilities
Authentication and rate limiting for API endpoints.
"""

import time
from typing import Optional
from fastapi import Header, HTTPException, status
from collections import defaultdict


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def check(self, client_id: str):
        """Check if client has exceeded rate limit."""
        now = time.time()
        # Clean old requests
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.window_seconds
        ]
        
        if len(self.requests[client_id]) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded"
            )
        
        self.requests[client_id].append(now)


# Global rate limiter instance
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)


async def get_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    """
    Extract user ID from Neon Auth header.
    Raises 401 if not authenticated.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return x_user_id


async def get_optional_user_id(x_user_id: Optional[str] = Header(None)) -> Optional[str]:
    """
    Extract user ID from Neon Auth header.
    Returns None if not authenticated (does not raise exception).
    """
    return x_user_id
