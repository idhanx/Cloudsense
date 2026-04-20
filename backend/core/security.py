"""
CloudSense — Security Utilities
Authentication and rate limiting for API endpoints.
"""

import time
from typing import Optional
from fastapi import Header, HTTPException, status
from collections import defaultdict


class RateLimiter:
    """In-memory rate limiter with automatic TTL-based eviction (prevents memory leaks).
    
    Uses TTLCache to automatically expire old entries instead of manual cleanup,
    preventing unbounded memory growth under high traffic.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60, max_clients: int = 10000):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self.requests: defaultdict = defaultdict(list)
        self._created_at: dict = {}  # Track when each client first appeared
        self._client_count: int = 0

    def _cleanup_old_clients(self):
        """Remove clients exceeding max_clients to prevent unbounded growth.
        
        This ensures the dictionary doesn't grow beyond max_clients entries,
        even under sustained traffic from many different IPs/users.
        """
        now = time.time()
        # Remove clients with no requests in the last window
        stale_clients = [
            client_id for client_id, times in self.requests.items()
            if not times or (now - max(times)) > self.window_seconds
        ]
        for client_id in stale_clients:
            del self.requests[client_id]
            if client_id in self._created_at:
                del self._created_at[client_id]
        
        # If still over limit, remove oldest clients
        if len(self.requests) > self.max_clients:
            # Sort by most recent request and remove oldest
            sorted_clients = sorted(
                self.requests.items(),
                key=lambda x: max(x[1]) if x[1] else 0
            )
            for client_id, _ in sorted_clients[:len(self.requests) - self.max_clients]:
                del self.requests[client_id]
                if client_id in self._created_at:
                    del self._created_at[client_id]

    def check(self, client_id: str):
        """Check if client has exceeded rate limit."""
        now = time.time()
        
        # Periodically clean up old entries (every 100 requests)
        if len(self.requests) % 100 == 0:
            self._cleanup_old_clients()
        
        # Remove entries outside the time window
        if client_id in self.requests:
            self.requests[client_id] = [t for t in self.requests[client_id] if now - t < self.window_seconds]
        else:
            self._created_at[client_id] = now

        if len(self.requests[client_id]) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
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
