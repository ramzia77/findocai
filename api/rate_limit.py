from __future__ import annotations

import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from api.auth import API_KEY_HEADER


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float):
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def try_consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimitMiddleware:
    """Plain ASGI middleware (not starlette.middleware.base.BaseHTTPMiddleware
    -- see AuditMiddleware's docstring in api/auth.py for why that class is
    avoided here) enforcing a per-API-key token-bucket rate limit.

    Unauthenticated/unrecognized keys share buckets keyed by client IP
    instead of being exempt -- auth will 401 them anyway, but this stops a
    raw connection flood from reaching the app at all.

    In-memory and per-process by design at this scale: a real multi-instance
    deployment would move this state to Redis (INCR + EXPIRE, or a Lua token
    bucket) so limits are enforced across replicas, not per-replica."""

    def __init__(self, app, requests_per_minute: int, enabled: bool = True):
        self.app = app
        self.enabled = enabled
        self.capacity = max(requests_per_minute, 1)
        self.refill_per_second = self.capacity / 60.0
        self._buckets: dict[str, TokenBucket] = {}

    def _bucket_for(self, key: str) -> TokenBucket:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_per_second)
            self._buckets[key] = bucket
        return bucket

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        api_key = request.headers.get(API_KEY_HEADER)
        client_host = request.client.host if request.client else "unknown"
        bucket_key = f"key:{api_key}" if api_key else f"ip:{client_host}"

        if not self._bucket_for(bucket_key).try_consume():
            response = JSONResponse(
                {"detail": "Rate limit exceeded, try again shortly"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
