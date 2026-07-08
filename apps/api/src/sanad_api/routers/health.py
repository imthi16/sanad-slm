"""GET /healthz (liveness: process) · GET /readyz (readiness: DB + Redis + ≥1 upstream)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    engine = getattr(request.app.state, "engine", None)
    try:
        assert engine is not None
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    redis = getattr(request.app.state, "redis", None)
    try:
        assert redis is not None
        await redis.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    model_router = getattr(request.app.state, "router", None)
    checks["upstream"] = bool(model_router and model_router.any_healthy)

    ready = all(checks.values())
    response.status_code = 200 if ready else 503
    return {"ready": ready, "checks": checks}
