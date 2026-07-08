"""Security middleware + auth dependencies (§7.1, §10).

- Security headers: CSP self-only, X-Content-Type-Options, HSTS outside dev.
- Bearer service-token dependency for machine ingestion endpoints.
- Redis token-bucket rate limit (per-IP dev, per-key prod) as a router dependency.
"""

from __future__ import annotations

import hmac
import time
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

_CSP = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, *, hsts: bool) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", _CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


async def require_service_token(request: Request) -> None:
    """Machine-to-machine bearer auth (eval-job ingestion)."""
    settings = request.app.state.settings
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, settings.service_token):
        raise HTTPException(status_code=401, detail="invalid service token")


ServiceToken = Annotated[None, Depends(require_service_token)]

# Atomic token bucket: one round-trip, refill computed in Redis time.
_BUCKET_LUA = """
local key      = KEYS[1]
local rate     = tonumber(ARGV[1])
local burst    = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])
local tokens   = tonumber(redis.call('HGET', key, 'tokens') or burst)
local ts       = tonumber(redis.call('HGET', key, 'ts') or now)
tokens = math.min(burst, tokens + (now - ts) * rate)
local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(burst / rate) * 2)
return allowed
"""


async def rate_limit(request: Request) -> None:
    settings = request.app.state.settings
    redis = getattr(request.app.state, "redis", None)
    if redis is None:  # tests / degraded mode: fail open, never fail closed on infra
        return
    api_key = request.headers.get("X-API-Key")
    ident = (
        api_key
        if (api_key and settings.mode != "dev")
        else (request.client.host if request.client else "anon")
    )
    allowed = await redis.eval(
        _BUCKET_LUA,
        1,
        f"rl:{ident}",
        str(settings.rate_limit_rps),
        str(settings.rate_limit_burst),
        str(time.time()),
    )
    if not int(allowed):
        raise HTTPException(status_code=429, detail="rate limit exceeded")


RateLimited = Annotated[None, Depends(rate_limit)]
