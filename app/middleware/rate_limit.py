import time
import logging
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.config import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware to prevent abuse."""
    
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self.requests: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        self.max_requests = settings.rate_limit_requests
        self.window_seconds = settings.rate_limit_window_sec
        logger.info(f"Rate limiting {'enabled' if enabled else 'disabled'}: "
                   f"{self.max_requests} requests per {self.window_seconds}s")
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get unique identifier for the client."""
        # Use X-Forwarded-For header if available (for reverse proxy scenarios)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Fallback to direct client host
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _is_rate_limited(self, client_id: str) -> bool:
        """Check if client has exceeded rate limit."""
        current_time = time.time()
        request_count, window_start = self.requests[client_id]
        
        # Check if we're in a new time window
        if current_time - window_start > self.window_seconds:
            # Reset counter for new window
            self.requests[client_id] = (1, current_time)
            return False
        
        # Increment counter in current window
        if request_count >= self.max_requests:
            return True
        
        self.requests[client_id] = (request_count + 1, window_start)
        return False
    
    def _cleanup_old_entries(self):
        """Periodically cleanup old entries to prevent memory leak."""
        current_time = time.time()
        expired_clients = [
            client_id for client_id, (_, window_start) in self.requests.items()
            if current_time - window_start > self.window_seconds * 2
        ]
        
        for client_id in expired_clients:
            del self.requests[client_id]
        
        if expired_clients:
            logger.debug(f"Cleaned up {len(expired_clients)} expired rate limit entries")
    
    async def dispatch(self, request: Request, call_next):
        """Process the request and apply rate limiting."""
        if not self.enabled:
            return await call_next(request)
        
        # Skip rate limiting for health check endpoint
        if request.url.path == "/health":
            return await call_next(request)
        
        client_id = self._get_client_identifier(request)
        
        # Check rate limit
        if self._is_rate_limited(client_id):
            logger.warning(f"Rate limit exceeded for client: {client_id}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Maximum {self.max_requests} requests per {self.window_seconds} seconds"
                },
                headers={
                    "Retry-After": str(self.window_seconds)
                }
            )
        
        # Periodically cleanup (every ~100 requests)
        if len(self.requests) % 100 == 0:
            self._cleanup_old_entries()
        
        response = await call_next(request)
        
        # Add rate limit headers to response
        client_request_count, _ = self.requests[client_id]
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.max_requests - client_request_count))
        response.headers["X-RateLimit-Window"] = str(self.window_seconds)
        
        return response

