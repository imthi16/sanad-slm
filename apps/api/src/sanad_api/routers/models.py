"""GET /v1/models — aliases + upstream health + quant format + license (§7.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["models"])


@router.get("/v1/models")
async def list_models(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    upstreams = request.app.state.router.list()
    return {
        "object": "list",
        "data": [
            {
                "id": u.alias,
                "object": "model",
                "owned_by": "sanad",
                "x_sanad": {
                    "upstream_kind": u.kind,
                    "healthy": u.healthy,
                    "quant_format": u.quant_format,
                    "license": u.license,
                    "sovereign": settings.mode != "dev",
                    "mode": settings.mode,
                },
            }
            for u in upstreams
        ],
    }
