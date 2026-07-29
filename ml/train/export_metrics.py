"""Export one MLflow training run to a committable, hashable JSON report (prime directive 6).

`sft.py` logs loss, VRAM, wall time and FLOPs to MLflow, whose backing store is a SQLite file
that is **not** in git (it lives in the artifact archive alongside the weights). So every training
figure quoted in RESULTS.md — peak VRAM, the 44-minute wall time, the loss curve — used to trace
only to a run id inside an untracked database. That is not traceability: nobody pulling this repo
can check the number. This script lifts the run out of the tracking store into a report that *is*
committed and *is* hashed, which is the same contract the eval reports already meet.

Read with stdlib `sqlite3` rather than `mlflow.MlflowClient` deliberately: the input is an archived
database file, possibly written by a different MLflow version than the one installed, and the four
tables involved (`runs`, `params`, `metrics`, `experiments`) are stable. No server, no client
version match, no import of the training stack.

**The output is byte-deterministic** — sorted keys, no generation timestamp, floats passed through
unrounded — so re-running it on the same run reproduces the same sha256. A report whose hash
changed on every export could not be cited by hash.

Usage:
    uv run python train/export_metrics.py --run-id b8ccaafc            # prefix is enough
    uv run python train/export_metrics.py --tracking-db ~/archive/mlflow.db --run-id b8ccaafc
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[1]

#: Hyperparameters and provenance worth committing. MLflow captures the entire
#: `TrainingArguments` surface (300+ keys, most of them defaults nobody set); a report that dumps
#: all of them buries the fifteen values that actually define the run. Everything here is either
#: quoted in RESULTS.md §4 or needed to re-run the config.
PARAM_KEYS = (
    "base_model",
    "revision",
    "config_sha256",
    "seed",
    "max_seq_len",
    "lora_r",
    "use_dora",
    "target_modules",
    "epochs",
    "lr",
    "lr_scheduler_type",
    "warmup_ratio",
    "per_device_train_batch_size",
    "gradient_accumulation_steps",
    "effective_batch",
    "packing",
    "optim",
    "neftune_noise_alpha",
    "bf16",
    "unsloth_version",
    "transformers_version",
)

#: Run-level summary metrics: logged once, at step 0 or at the end of training.
SUMMARY_METRIC_KEYS = (
    "peak_vram_gb",
    "train_hours",
    "train_runtime",
    "train_loss",
    "eval_loss",
    "total_flos",
    "train_samples_per_second",
    "train_steps_per_second",
    "epoch",
)

#: Per-step series: the loss curve and its schedule. These are what make the training claim
#: checkable rather than assertable.
HISTORY_METRIC_KEYS = ("loss", "eval_loss", "learning_rate", "grad_norm")


class ExportError(RuntimeError):
    """The requested run is not in this tracking store, or is ambiguous."""


def resolve_run(conn: sqlite3.Connection, run_id: str) -> tuple[str, str, str, int, int, str]:
    """Resolve a run id *prefix* to exactly one run. Ambiguity is an error, not a first match."""
    rows = list(
        conn.execute(
            "SELECT r.run_uuid, r.name, r.status, r.start_time, r.end_time, e.name "
            "FROM runs r JOIN experiments e ON e.experiment_id = r.experiment_id "
            "WHERE r.run_uuid LIKE ? AND r.lifecycle_stage = 'active'",
            (f"{run_id}%",),
        )
    )
    if not rows:
        raise ExportError(f"no active run matching {run_id!r} in this tracking store")
    if len(rows) > 1:
        matches = ", ".join(r[0] for r in rows)
        raise ExportError(f"run id prefix {run_id!r} is ambiguous: {matches}")
    uuid, name, status, start, end, experiment = rows[0]
    return str(uuid), str(name), str(status), int(start), int(end), str(experiment)


def _iso(ms: int) -> str:
    """MLflow stores epoch milliseconds; a report should carry a readable UTC instant."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat(timespec="seconds")


def _params(conn: sqlite3.Connection, uuid: str) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM params WHERE run_uuid = ?", (uuid,))
    found = {str(k): str(v) for k, v in rows}
    return {k: found[k] for k in PARAM_KEYS if k in found}


def _summary_metrics(conn: sqlite3.Connection, uuid: str) -> dict[str, float]:
    rows = conn.execute(
        "SELECT key, value FROM latest_metrics WHERE run_uuid = ? AND is_nan = 0", (uuid,)
    )
    found = {str(k): float(v) for k, v in rows}
    return {k: found[k] for k in SUMMARY_METRIC_KEYS if k in found}


def _history(conn: sqlite3.Connection, uuid: str) -> dict[str, list[dict[str, float]]]:
    history: dict[str, list[dict[str, float]]] = {}
    for key in HISTORY_METRIC_KEYS:
        rows = conn.execute(
            "SELECT step, value FROM metrics WHERE run_uuid = ? AND key = ? AND is_nan = 0 "
            "ORDER BY step",
            (uuid, key),
        )
        series = [{"step": int(step), "value": float(value)} for step, value in rows]
        if series:
            history[key] = series
    return history


def build_report(db: Path, run_id: str) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        uuid, name, status, start, end, experiment = resolve_run(conn, run_id)
        summary = _summary_metrics(conn, uuid)
        report: dict[str, Any] = {
            "schema": "sanad.train_metrics/v1",
            "source": {
                "tracking_store": "mlflow sqlite (not in git — see RESULTS.md §Traceability)",
                "experiment": experiment,
                "run_id": uuid,
                "run_name": name,
                "status": status,
                "started_utc": _iso(start),
                "ended_utc": _iso(end),
                "wall_clock_seconds": round((end - start) / 1000, 3),
            },
            "params": _params(conn, uuid),
            "metrics": summary,
            "metric_history": _history(conn, uuid),
            "cost": {
                "usd_actual": 0.0,
                "basis": (
                    "local RTX 4090 workstation, ADR-0003/0004 — no compute was purchased. "
                    "MLflow's cost_usd metric is a cloud-equivalent estimate "
                    "(train_hours x SANAD_GPU_USD_HR, default $0.60/h) and is not a spend."
                ),
            },
            "notes": (
                "wall_clock_seconds spans process start to finish (model load, merge, save); "
                "metrics.train_runtime is the SFTTrainer training loop alone, and is the figure "
                "quoted as wall time."
            ),
        }
        return report
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tracking-db",
        type=Path,
        default=ML_ROOT / "mlflow.db",
        help="MLflow SQLite backing store (default: ml/mlflow.db)",
    )
    ap.add_argument("--run-id", required=True, help="run id or unique prefix")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output path (default: evals/reports/train_metrics_<run-id-prefix>.json)",
    )
    args = ap.parse_args()

    db: Path = args.tracking_db.expanduser()
    if not db.exists():
        raise SystemExit(f"tracking store not found: {db}")

    report = build_report(db, args.run_id)
    short = report["source"]["run_id"][:8]
    out: Path = args.out or ML_ROOT / "evals" / "reports" / f"train_metrics_{short}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic bytes: sorted keys, fixed separators, trailing newline. The sha256 of this
    # file is cited in RESULTS.md, so identical input must give identical output.
    out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    log.info(
        "train_metrics_exported",
        out=str(out),
        run_id=report["source"]["run_id"],
        peak_vram_gb=report["metrics"].get("peak_vram_gb"),
        train_runtime=report["metrics"].get("train_runtime"),
    )


if __name__ == "__main__":
    main()
