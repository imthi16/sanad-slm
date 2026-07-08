"""Ingest eval reports (domain, judge_3c3h, agreement, fertility) into the DB (§7.2)."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from sanad_api.db.models import AgreementStats, BenchmarkScore, EvalRun, JudgeScore

log = structlog.get_logger()

JUDGE_DIMS = ["completeness", "conciseness", "helpfulness", "honesty", "harmlessness"]


async def ingest_reports(
    session: AsyncSession, run_id: str, reports: dict[str, Any]
) -> dict[str, int]:
    counts = {"benchmark_scores": 0, "judge_scores": 0}

    run = await session.get(EvalRun, run_id)
    if run is None:
        run = EvalRun(id=run_id)
        session.add(run)
    else:
        # idempotent re-ingest: replace prior rows for this run
        await session.execute(delete(BenchmarkScore).where(BenchmarkScore.run_id == run_id))
        await session.execute(delete(JudgeScore).where(JudgeScore.run_id == run_id))
        await session.execute(delete(AgreementStats).where(AgreementStats.run_id == run_id))

    if domain := reports.get("domain_finetuned"):
        run.model_version = domain.get("model")
        for metric, value in (domain.get("scores") or {}).items():
            if value is None:
                continue
            session.add(
                BenchmarkScore(
                    run_id=run_id,
                    task="domain_bank_v1",
                    model=domain.get("model", "finetuned"),
                    metric=metric,
                    value=float(value),
                )
            )
            counts["benchmark_scores"] += 1
        if (agg := domain.get("aggregate_score")) is not None:
            session.add(
                BenchmarkScore(
                    run_id=run_id,
                    task="domain_bank_v1",
                    model=domain.get("model", "finetuned"),
                    metric="aggregate",
                    value=float(agg),
                )
            )
            counts["benchmark_scores"] += 1

    if judge := reports.get("judge_3c3h"):
        for row in judge.get("rows", []):
            base = {
                "run_id": run_id,
                "item_id": row["item_id"],
                "judge": row["judge"],
                "sovereign": bool(row.get("sovereign", True)),
                "lang": row.get("lang"),
            }
            session.add(JudgeScore(**base, dimension="correct", score=float(row["correct"])))
            session.add(JudgeScore(**base, dimension="final", score=float(row["final"])))
            counts["judge_scores"] += 2
            for d in JUDGE_DIMS:
                if d in row:
                    session.add(JudgeScore(**base, dimension=d, score=float(row[d])))
                    counts["judge_scores"] += 1

    if agreement := reports.get("agreement"):
        session.add(
            AgreementStats(
                run_id=run_id,
                krippendorff_alpha=agreement.get("krippendorff_alpha", {}),
                pairwise_cohens_kappa=agreement.get("pairwise_cohens_kappa", {}),
                heatmap={"cells": agreement.get("heatmap", [])},
                human_queue_count=int(agreement.get("human_queue", {}).get("count", 0)),
                human_judge_kappa=agreement.get("human_judge_kappa"),
            )
        )

    if efficiency := reports.get("efficiency"):
        run.efficiency = efficiency
    if provenance := reports.get("provenance_split"):
        run.provenance_split = provenance

    await session.commit()
    log.info("reports_ingested", run_id=run_id, **counts)
    return counts
