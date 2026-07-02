"""Eval run resources: benchmark scores, 3C3H per-dim, agreement stats, efficiency (§7.2)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class BenchmarkScore(BaseModel):
    task: str  # arabicmmlu | aratrust | madinahqa | alrage | domain_bank_v1
    model: str
    metric: str
    value: float
    measured_locally: bool = True  # vendor numbers are quoted only next to re-measured ones


class JudgeDimension(BaseModel):
    dimension: str  # completeness | conciseness | helpfulness | honesty | harmlessness
    score: float = Field(ge=0, le=5)


class JudgeSummary(BaseModel):
    headline_final: float
    correct_rate: float
    per_dimension: list[JudgeDimension]
    judges: list[str]
    sovereign_only: bool = True
    human_judge_kappa: float | None = None  # judge claims require this (directive 5)


class HeatmapCell(BaseModel):
    judge: str
    dimension: str
    mean_abs_dev: float


class AgreementStats(BaseModel):
    krippendorff_alpha: dict[str, float | None]  # overall + per-dimension
    pairwise_cohens_kappa: dict[str, float | None]
    heatmap: list[HeatmapCell]
    human_queue_count: int = 0


class EfficiencyPanel(BaseModel):
    ttft_ms: float | None = None
    tokens_per_second: float | None = None
    peak_vram_gb: float | None = None
    peak_rss_gb: float | None = None
    watts: float | None = None
    usd_per_1m_output_tokens: float | None = None


class EvalRun(BaseModel):
    id: str
    created_at: dt.datetime
    model_version: str | None = None
    provenance_split: dict[str, float] | None = None  # printed into every report (§5.1)
    benchmark_scores: list[BenchmarkScore] = []
    judge: JudgeSummary | None = None
    agreement: AgreementStats | None = None
    efficiency: EfficiencyPanel | None = None


class EvalRunListItem(BaseModel):
    id: str
    created_at: dt.datetime
    model_version: str | None = None
    headline: dict[str, float] = {}


class IngestPayload(BaseModel):
    run_id: str
    reports: dict[str, Any]  # raw report JSONs keyed by name (domain_finetuned, judge_3c3h, …)
