"""Registry service + router: MinIO manifest listing, cosign flag, lineage graph (§5.5, §7.2)."""

from __future__ import annotations

import io
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from sanad_api.core.config import Settings
from sanad_api.services import registry as registry_service
from sanad_api.services.registry import lineage_graph, list_artifacts


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


MANIFEST = {
    "base_model": "Qwen/Qwen3-4B-Instruct-2507",
    "base_revision": "abc12345def67890",
    "data_manifest_sha256": "d" * 64,
    "eval_report_sha256": "e" * 64,
    "artifact_sha256": "a" * 64,
    "licenses": ["Apache-2.0"],
    "created_at": "2026-07-15T00:00:00Z",
}


class _FakePaginator:
    def paginate(self, **_: Any) -> list[dict[str, Any]]:
        return [{"CommonPrefixes": [{"Prefix": "sanad-qwen3-4b-bank/"}]}]


class _FakeS3:
    """v0.1.0: manifest + sig present; v0.2.0: neither (error paths)."""

    def get_paginator(self, name: str) -> _FakePaginator:
        return _FakePaginator()

    def list_objects_v2(self, *, Bucket: str, Prefix: str, Delimiter: str) -> dict[str, Any]:
        return {"CommonPrefixes": [{"Prefix": f"{Prefix}0.1.0/"}, {"Prefix": f"{Prefix}0.2.0/"}]}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if "0.2.0" in Key:
            raise RuntimeError("NoSuchKey")
        return {"Body": io.BytesIO(json.dumps(MANIFEST).encode())}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if "0.2.0" in Key:
            raise RuntimeError("404")
        return {}


@pytest.mark.anyio
async def test_list_artifacts_reads_manifests_and_sig(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry_service, "_client", lambda s: _FakeS3())
    artifacts = await list_artifacts(settings)
    assert [a["version"] for a in artifacts] == ["0.1.0", "0.2.0"]

    signed = artifacts[0]
    assert signed["model_name"] == "sanad-qwen3-4b-bank"
    assert signed["sha256"] == "a" * 64
    assert signed["cosign_signed"] is True
    assert signed["licenses"] == ["Apache-2.0"]

    unsigned = artifacts[1]
    assert unsigned["manifest"] is None
    assert unsigned["sha256"] is None
    assert unsigned["cosign_signed"] is False
    assert unsigned["licenses"] == []


@pytest.mark.anyio
async def test_list_artifacts_degrades_to_empty_when_unreachable(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(s: Settings) -> Any:
        raise ConnectionError("minio down")

    monkeypatch.setattr(registry_service, "_client", _boom)
    assert await list_artifacts(settings) == []


def test_lineage_graph_dedupes_shared_nodes() -> None:
    artifacts = [
        {"model_name": "m", "version": "0.1.0", "cosign_signed": True, "manifest": MANIFEST},
        {"model_name": "m", "version": "0.2.0", "cosign_signed": False, "manifest": MANIFEST},
        {"model_name": "m", "version": "0.3.0", "cosign_signed": False, "manifest": None},
    ]
    graph = lineage_graph(artifacts)
    ids = [n["id"] for n in graph["nodes"]]
    assert len(ids) == len(set(ids))  # deduped
    assert "Qwen/Qwen3-4B-Instruct-2507@abc12345" in ids  # shared base appears once
    assert f"data@{'d' * 8}" in ids
    labels = {e["label"] for e in graph["edges"]}
    assert labels == {"fine-tuned", "trained-on", "evaluated-by"}
    # both manifested versions get all three edges; the manifest-less one gets none
    assert len(graph["edges"]) == 6


@pytest.mark.anyio
async def test_artifacts_route_shape(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    canned = [
        {
            "model_name": "sanad-qwen3-4b-bank",
            "version": "0.1.0",
            "manifest": MANIFEST,
            "sha256": "a" * 64,
            "cosign_signed": True,
            "licenses": ["Apache-2.0"],
        }
    ]

    async def _fake(settings: Settings) -> list[dict[str, Any]]:
        return canned

    monkeypatch.setattr("sanad_api.routers.registry.list_artifacts", _fake)
    r = await client.get("/v1/registry/artifacts")
    assert r.status_code == 200
    body = r.json()
    a = body["artifacts"][0]
    assert a["base_model"] == "Qwen/Qwen3-4B-Instruct-2507"
    assert a["created_at"] == "2026-07-15T00:00:00Z"
    assert a["cosign_signed"] is True
    assert body["lineage"]["nodes"] and body["lineage"]["edges"]
