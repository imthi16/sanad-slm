"""SQLAlchemy 2.0 declarative models (§7.3).

Tables: eval_runs, benchmark_scores, judge_scores, agreement_stats, artifacts,
telemetry_snapshots, chat_usage. Chat CONTENT is never persisted by default — only usage
metadata (sovereign posture; SANAD_PERSIST_CHATS=true adds a dev-only content column usage).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map: ClassVar = {dict[str, Any]: JSON}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_version: Mapped[str | None] = mapped_column(String(128))
    provenance_split: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    efficiency: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    benchmark_scores: Mapped[list[BenchmarkScore]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    judge_scores: Mapped[list[JudgeScore]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    agreement: Mapped[AgreementStats | None] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False
    )


class BenchmarkScore(Base):
    __tablename__ = "benchmark_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True)
    task: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    metric: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    measured_locally: Mapped[bool] = mapped_column(Boolean, default=True)

    run: Mapped[EvalRun] = relationship(back_populates="benchmark_scores")


class JudgeScore(Base):
    __tablename__ = "judge_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    judge: Mapped[str] = mapped_column(String(64))
    dimension: Mapped[str] = mapped_column(String(32))  # correct|final|completeness|…
    score: Mapped[float] = mapped_column(Float)
    sovereign: Mapped[bool] = mapped_column(Boolean, default=True)  # False ⇒ excluded from headline
    lang: Mapped[str | None] = mapped_column(String(8))

    run: Mapped[EvalRun] = relationship(back_populates="judge_scores")


class AgreementStats(Base):
    __tablename__ = "agreement_stats"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), primary_key=True
    )
    krippendorff_alpha: Mapped[dict[str, Any]] = mapped_column(JSON)
    pairwise_cohens_kappa: Mapped[dict[str, Any]] = mapped_column(JSON)
    heatmap: Mapped[dict[str, Any]] = mapped_column(JSON)  # {"cells": [...]}
    human_queue_count: Mapped[int] = mapped_column(Integer, default=0)
    human_judge_kappa: Mapped[float | None] = mapped_column(Float)

    run: Mapped[EvalRun] = relationship(back_populates="agreement")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # adapter|merged-bf16|awq-w4a16|gguf
    sha256: Mapped[str | None] = mapped_column(String(64))
    cosign_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # manifest.json content
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelemetrySnapshot(Base):
    __tablename__ = "telemetry_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    watts: Mapped[float | None] = mapped_column(Float)
    gpu_util_pct: Mapped[float | None] = mapped_column(Float)
    temp_c: Mapped[float | None] = mapped_column(Float)
    tokens_per_second: Mapped[float | None] = mapped_column(Float)
    mem_used_gb: Mapped[float | None] = mapped_column(Float)


class ChatUsage(Base):
    __tablename__ = "chat_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    model_alias: Mapped[str] = mapped_column(String(64))
    upstream: Mapped[str] = mapped_column(String(16))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ttft_ms: Mapped[float | None] = mapped_column(Float)
    tokens_per_second: Mapped[float | None] = mapped_column(Float)
    detected_lang: Mapped[str | None] = mapped_column(String(8))
    # dev-only (SANAD_PERSIST_CHATS=true); ALWAYS null in sovereign mode
    content: Mapped[str | None] = mapped_column(Text, default=None)
