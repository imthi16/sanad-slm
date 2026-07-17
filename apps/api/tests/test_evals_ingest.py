"""Eval ingestion round-trip: POST reports → GET runs/detail (§7.2, judge_ingest service)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _auth(app: FastAPI) -> dict[str, str]:
    return {"Authorization": f"Bearer {app.state.settings.service_token}"}


def _payload(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "reports": {
            "domain_finetuned": {
                "model": "sanad-qwen3-4b-bank@0.1.0",
                "scores": {"extraction_f1": 0.81, "classification_acc": 0.9, "skipped": None},
                "aggregate_score": 0.85,
            },
            "judge_3c3h": {
                "rows": [
                    {
                        "item_id": "bank-ar-0001",
                        "judge": "falcon-h1-7b",
                        "correct": 1.0,
                        "final": 4.2,
                        "completeness": 4,
                        "conciseness": 5,
                        "helpfulness": 4,
                        "honesty": 5,
                        "harmlessness": 5,
                        "lang": "ar",
                    },
                    {
                        "item_id": "bank-ar-0001",
                        "judge": "allam-7b",
                        "correct": 1.0,
                        "final": 3.8,
                        "completeness": 4,
                        "lang": "ar",
                    },
                    # API judge: sovereign=False ⇒ must never enter headline numbers (§5.4c)
                    {
                        "item_id": "bank-ar-0001",
                        "judge": "frontier-api",
                        "correct": 1.0,
                        "final": 5.0,
                        "sovereign": False,
                        "lang": "ar",
                    },
                ]
            },
            "agreement": {
                "krippendorff_alpha": {"overall": 0.71},
                "pairwise_cohens_kappa": {"falcon-h1-7b|allam-7b": 0.66},
                "heatmap": [{"judge": "falcon-h1-7b", "dimension": "honesty", "mean_abs_dev": 0.4}],
                "human_queue": {"count": 3},
                "human_judge_kappa": 0.74,
            },
            "efficiency": {"ttft_ms": 180.0, "tokens_per_second": 42.5},
            "provenance_split": {"native": 0.72, "translated": 0.18, "synthetic": 0.10},
        },
    }


@pytest.mark.anyio
async def test_ingest_rejects_bad_token(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    r = await client.post(
        "/v1/eval/runs/r1/ingest",
        json=_payload("r1"),
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


@pytest.mark.anyio
async def test_ingest_rejects_run_id_mismatch(
    client: httpx.AsyncClient, app: FastAPI, db: async_sessionmaker[AsyncSession]
) -> None:
    r = await client.post("/v1/eval/runs/r1/ingest", json=_payload("other"), headers=_auth(app))
    assert r.status_code == 422


@pytest.mark.anyio
async def test_ingest_then_get_run_detail(
    client: httpx.AsyncClient, app: FastAPI, db: async_sessionmaker[AsyncSession]
) -> None:
    r = await client.post("/v1/eval/runs/r1/ingest", json=_payload("r1"), headers=_auth(app))
    assert r.status_code == 202
    counts = r.json()["ingested"]
    # 2 metrics (None dropped) + aggregate; judge rows: (2+5) + (2+1) + (2+0)
    assert counts == {"benchmark_scores": 3, "judge_scores": 12}

    detail = (await client.get("/v1/eval/runs/r1")).json()
    assert detail["model_version"] == "sanad-qwen3-4b-bank@0.1.0"
    assert detail["provenance_split"]["native"] == 0.72
    assert len(detail["benchmark_scores"]) == 3

    judge = detail["judge"]
    assert sorted(judge["judges"]) == ["allam-7b", "falcon-h1-7b"]  # sovereign only
    assert judge["headline_final"] == pytest.approx(4.0)
    assert judge["correct_rate"] == pytest.approx(1.0)
    assert judge["human_judge_kappa"] == pytest.approx(0.74)
    dims = {d["dimension"]: d["score"] for d in judge["per_dimension"]}
    assert dims["completeness"] == pytest.approx(4.0)
    assert dims["honesty"] == pytest.approx(5.0)

    agreement = detail["agreement"]
    assert agreement["krippendorff_alpha"]["overall"] == pytest.approx(0.71)
    assert agreement["heatmap"][0]["judge"] == "falcon-h1-7b"
    assert agreement["human_queue_count"] == 3

    assert detail["efficiency"]["ttft_ms"] == pytest.approx(180.0)


@pytest.mark.anyio
async def test_reingest_is_idempotent(
    client: httpx.AsyncClient, app: FastAPI, db: async_sessionmaker[AsyncSession]
) -> None:
    for _ in range(2):
        r = await client.post("/v1/eval/runs/r1/ingest", json=_payload("r1"), headers=_auth(app))
        assert r.status_code == 202
        assert r.json()["ingested"] == {"benchmark_scores": 3, "judge_scores": 12}

    detail = (await client.get("/v1/eval/runs/r1")).json()
    assert len(detail["benchmark_scores"]) == 3  # replaced, not duplicated


@pytest.mark.anyio
async def test_list_runs_headline(
    client: httpx.AsyncClient, app: FastAPI, db: async_sessionmaker[AsyncSession]
) -> None:
    await client.post("/v1/eval/runs/r1/ingest", json=_payload("r1"), headers=_auth(app))
    runs = (await client.get("/v1/eval/runs")).json()
    assert len(runs) == 1
    # headline keeps only aggregate/acc metrics
    assert runs[0]["headline"] == {"domain_bank_v1:aggregate": 0.85}


@pytest.mark.anyio
async def test_get_unknown_run_is_404(
    client: httpx.AsyncClient, db: async_sessionmaker[AsyncSession]
) -> None:
    r = await client.get("/v1/eval/runs/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
