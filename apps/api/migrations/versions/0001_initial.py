"""initial schema — eval_runs, benchmark_scores, judge_scores, agreement_stats, artifacts,
telemetry_snapshots, chat_usage (§7.3)

Revision ID: 0001
Revises:
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=True),
        sa.Column("provenance_split", sa.JSON(), nullable=True),
        sa.Column("efficiency", sa.JSON(), nullable=True),
    )
    op.create_table(
        "benchmark_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("eval_runs.id", ondelete="CASCADE")),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("measured_locally", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_benchmark_scores_run_id", "benchmark_scores", ["run_id"])
    op.create_table(
        "judge_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("eval_runs.id", ondelete="CASCADE")),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("judge", sa.String(64), nullable=False),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("sovereign", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("lang", sa.String(8), nullable=True),
    )
    op.create_index("ix_judge_scores_run_id", "judge_scores", ["run_id"])
    op.create_index("ix_judge_scores_item_id", "judge_scores", ["item_id"])
    op.create_table(
        "agreement_stats",
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("krippendorff_alpha", sa.JSON(), nullable=False),
        sa.Column("pairwise_cohens_kappa", sa.JSON(), nullable=False),
        sa.Column("heatmap", sa.JSON(), nullable=False),
        sa.Column("human_queue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("human_judge_kappa", sa.Float(), nullable=True),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("cosign_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_model_name", "artifacts", ["model_name"])
    op.create_index("ix_artifacts_version", "artifacts", ["version"])
    op.create_table(
        "telemetry_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("watts", sa.Float(), nullable=True),
        sa.Column("gpu_util_pct", sa.Float(), nullable=True),
        sa.Column("temp_c", sa.Float(), nullable=True),
        sa.Column("tokens_per_second", sa.Float(), nullable=True),
        sa.Column("mem_used_gb", sa.Float(), nullable=True),
    )
    op.create_index("ix_telemetry_snapshots_source", "telemetry_snapshots", ["source"])
    op.create_index("ix_telemetry_snapshots_ts", "telemetry_snapshots", ["ts"])
    op.create_table(
        "chat_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_alias", sa.String(64), nullable=False),
        sa.Column("upstream", sa.String(16), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ttft_ms", sa.Float(), nullable=True),
        sa.Column("tokens_per_second", sa.Float(), nullable=True),
        sa.Column("detected_lang", sa.String(8), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),  # dev-only; null in sovereign mode
    )
    op.create_index("ix_chat_usage_ts", "chat_usage", ["ts"])


def downgrade() -> None:
    for table in (
        "chat_usage",
        "telemetry_snapshots",
        "artifacts",
        "agreement_stats",
        "judge_scores",
        "benchmark_scores",
        "eval_runs",
    ):
        op.drop_table(table)
