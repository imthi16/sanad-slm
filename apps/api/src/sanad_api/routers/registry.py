"""GET /v1/registry/artifacts — model versions, sha256, cosign status, lineage graph (§7.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from sanad_api.services.registry import lineage_graph, list_artifacts

router = APIRouter(prefix="/v1/registry", tags=["registry"])


@router.get("/artifacts")
async def artifacts(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    items = await list_artifacts(settings)
    return {
        "artifacts": [
            {
                "model_name": a["model_name"],
                "version": a["version"],
                "sha256": a["sha256"],
                "cosign_signed": a["cosign_signed"],
                "licenses": a["licenses"],
                "base_model": (a.get("manifest") or {}).get("base_model"),
                "created_at": (a.get("manifest") or {}).get("created_at"),
            }
            for a in items
        ],
        "lineage": lineage_graph(items),
    }
