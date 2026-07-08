from __future__ import annotations

import httpx
import pytest

from sanad_api.services.inference_router import detect_lang


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_detect_lang_matrix() -> None:
    assert detect_lang("ما هي متطلبات فتح الحساب؟") == "ar"
    assert detect_lang("what is the minimum balance") == "en"
    assert detect_lang("أبغى أفتح current account") == "mixed"
    assert detect_lang("12345") == "en"  # numerals default safely


@pytest.mark.anyio
async def test_models_lists_aliases_with_sanad_meta(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/models")
    assert r.status_code == 200
    data = r.json()["data"]
    aliases = {m["id"] for m in data}
    assert {"sanad-bank-awq", "sanad-bank-gguf"} <= aliases
    awq = next(m for m in data if m["id"] == "sanad-bank-awq")
    assert awq["x_sanad"]["upstream_kind"] == "vllm"
    assert awq["x_sanad"]["quant_format"] == "awq-w4a16"
    assert "healthy" in awq["x_sanad"]


@pytest.mark.anyio
async def test_healthz_liveness(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_readyz_reports_degraded_when_no_backends(client: httpx.AsyncClient) -> None:
    # test app has no DB/Redis and unhealthy upstreams → readiness must be 503, honestly
    r = await client.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert set(body["checks"]) == {"database", "redis", "upstream"}


@pytest.mark.anyio
async def test_ingest_requires_service_token(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/eval/runs/x/ingest", json={"run_id": "x", "reports": {}})
    assert r.status_code == 401
