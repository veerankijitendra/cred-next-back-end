import asyncio
import hashlib
import time
from collections import OrderedDict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings


class AuthRateLimiter:
    """Bounded per-process IP limiter for sensitive authentication routes.

    Production deployments with multiple workers must also enforce the same or
    stricter limits at a shared gateway because this in-process state is local.
    """

    def __init__(self, *, max_keys: int = 20_000) -> None:
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._max_keys = max_keys
        self._last_sweep = 0.0

    async def check(self, *, key: str, limit: int) -> int | None:
        now = time.monotonic()
        cutoff = now - settings.auth_rate_limit_window_seconds
        async with self._lock:
            if now - self._last_sweep >= settings.auth_rate_limit_window_seconds:
                for old_key in list(self._events):
                    events = self._events[old_key]
                    while events and events[0] <= cutoff:
                        events.popleft()
                    if not events:
                        del self._events[old_key]
                self._last_sweep = now

            events = self._events.pop(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                self._events[key] = events
                return max(1, int(settings.auth_rate_limit_window_seconds - (now - events[0])))
            events.append(now)
            self._events[key] = events
            while len(self._events) > self._max_keys:
                self._events.popitem(last=False)
            return None


rate_limiter = AuthRateLimiter()


async def enforce_auth_rate_limit(request: Request) -> JSONResponse | None:
    limits = {
        ("POST", "/api/v1/auth/login"): settings.login_rate_limit,
        ("POST", "/api/v1/auth/register"): settings.register_rate_limit,
        ("POST", "/api/v1/auth/verify-otp"): settings.otp_rate_limit,
        ("POST", "/api/v1/auth/resend-otp"): settings.otp_rate_limit,
        ("POST", "/api/v1/auth/refresh"): settings.refresh_rate_limit,
        ("POST", "/api/v1/auth/logout"): settings.refresh_rate_limit,
    }
    limit = limits.get((request.method.upper(), request.url.path))
    if limit is None:
        return None
    client_host = request.client.host if request.client else "unknown"
    digest = hashlib.sha256(f"{client_host}:{request.url.path}".encode()).hexdigest()
    retry_after = await rate_limiter.check(key=digest, limit=limit)
    if retry_after is None:
        return None
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        content={"success": False, "message": "Too many requests. Try again later.", "error_code": "TOO_MANY_REQUESTS"},
    )
