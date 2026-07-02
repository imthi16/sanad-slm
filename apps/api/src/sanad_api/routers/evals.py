"""Eval run resources + machine ingestion (§7.2).

GET /v1/eval/runs · GET /v1/eval/runs/{id} · POST /v1/eval/runs/{id}/ingest (service token).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sanad_api.core.security import ServiceToken
from sanad_api.db.models import EvalRun, JudgeScore
from sanad_api.db.session import get_session
from sanad_api.schemas.evals import (
    AgreementStats,
    EfficiencyPanel,
    EvalRunListItem,
    HeatmapCell,
    IngestPayload,
    JudgeDimension,
    JudgeSummary,
)
from sanad_api.schemas.evals import (
    BenchmarkScore as BenchmarkScoreSchema,
)
from sanad_api.services.judge_ingest import JUDGE_DIMS, ingest_reports

router = APIRouter(prefix="/v1/eval", tags=["evals"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/runs")
async def list_runs(session: Session) -> list[EvalRunListItem]:
    result = await session.execute(
        select(EvalRun)
        .options(selectinload(EvalRun.benchmark_scores))
        .order_by(EvalRun.created_at.desc())
    )
    items = []
    for run in result.scalars():
        headline = {
            f"{s.task}:{s.metric}": s.value
            for s in run.benchmark_scores
            if s.metric in ("aggregate", "acc")
        }
        items.append(
            EvalRunListItem(
                id=run.id,
                created_at=run.created_at,
                model_version=run.model_version,
                headline=headline,
            )
        )
    return items


def _judge_summary(scores: list[JudgeScore]) -> JudgeSummary | None:
    sov = [s for s in scores if s.sovereign]  # non-sovereign judges never enter headline (§5.4c)
    if not sov:
        return None
    finals = [s.score for s in sov if s.dimension == "final"]
    corrects = [s.score for s in sov if s.dimension == "correct"]
    per_dim = []
    for d in JUDGE_DIMS:
        vals = [s.score for s in sov if s.dimension == d]
        if vals:
            per_dim.append(JudgeDimension(dimension=d, score=sum(vals) / len(vals)))
    return JudgeSummary(
        headline_final=sum(finals) / len(finals) if finals else 0.0,
        correct_rate=sum(corrects) / len(corrects) if corrects else 0.0,
        per_dimension=per_dim,
        judges=sorted({s.judge for s in sov}),
    )


@router.get("/runs/{run_id}")
async def get_run(run_id: str, session: Session) -> dict[str, Any]:
    run = await session.get(
        EvalRun,
        run_id,
        options=[
            selectinload(EvalRun.benchmark_scores),
            selectinload(EvalRun.judge_scores),
            selectinload(EvalRun.agreement),
        ],
    )
    if run is None:
        raise HTTPException(status_code=404, detail=f"eval run '{run_id}' not found")

    judge = _judge_summary(run.judge_scores)
    agreement = None
    if run.agreement:
        if judge:
            judge.human_judge_kappa = run.agreement.human_judge_kappa
        agreement = AgreementStats(
            krippendorff_alpha=run.agreement.krippendorff_alpha,
            pairwise_cohens_kappa=run.agreement.pairwise_cohens_kappa,
            heatmap=[HeatmapCell(**c) for c in run.agreement.heatmap.get("cells", [])],
            human_queue_count=run.agreement.human_queue_count,
        )
    return {
        "id": run.id,
        "created_at": run.created_at,
        "model_version": run.model_version,
        "provenance_split": run.provenance_split,
        "benchmark_scores": [
            BenchmarkScoreSchema(
                task=s.task,
                model=s.model,
                metric=s.metric,
                value=s.value,
                measured_locally=s.measured_locally,
            )
            for s in run.benchmark_scores
        ],
        "judge": judge,
        "agreement": agreement,
        "efficiency": EfficiencyPanel(**run.efficiency) if run.efficiency else None,
    }


@router.post("/runs/{run_id}/ingest", status_code=202)
async def ingest(
    run_id: str, payload: IngestPayload, _: ServiceToken, session: Session, request: Request
) -> dict[str, Any]:
    # ServiceToken precedes Session: auth must reject before a DB session is acquired
    if payload.run_id != run_id:
        raise HTTPException(status_code=422, detail="payload run_id does not match path")
    counts = await ingest_reports(session, run_id, payload.reports)
    return {"run_id": run_id, "ingested": counts}
