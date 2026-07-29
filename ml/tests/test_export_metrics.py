"""`export_metrics.py` is what makes the training figures citable, so it needs its own guarantees.

Two properties matter and neither is obvious from reading the code:

1. **The output is byte-identical across runs.** RESULTS.md cites this report by sha256. If any
   part of the export varied — key order, a generation timestamp, float formatting — the citation
   would be dead on the next export, and "traced by hash" would be decoration.
2. **A run-id prefix that matches two runs is an error.** The training experiment holds four runs
   whose ids share no prefix today, but three of them FAILED; silently exporting a first match
   would be a way to publish the wrong run's numbers.

The fixture is a hand-built SQLite file with MLflow's column layout rather than a real tracking
store: the real one is 100 MB of archive that CI does not have, and the four tables read here are
the stable part of MLflow's schema.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from export_metrics import ExportError, build_report

SCHEMA = (
    "CREATE TABLE experiments (experiment_id INTEGER, name TEXT, lifecycle_stage TEXT)",
    "CREATE TABLE runs (run_uuid TEXT, name TEXT, status TEXT, start_time INTEGER, "
    "end_time INTEGER, experiment_id INTEGER, lifecycle_stage TEXT)",
    "CREATE TABLE params (key TEXT, value TEXT, run_uuid TEXT)",
    "CREATE TABLE metrics (key TEXT, value REAL, timestamp INTEGER, run_uuid TEXT, "
    "step INTEGER, is_nan INTEGER)",
    "CREATE TABLE latest_metrics (key TEXT, value REAL, timestamp INTEGER, run_uuid TEXT, "
    "step INTEGER, is_nan INTEGER)",
)

RUN = "b8ccaafcb55b45b6a0b09062e9d9d05e"


def _store(
    path: Path, runs: tuple[tuple[str, str, str], ...] = ((RUN, "shad-242", "FINISHED"),)
) -> None:
    conn = sqlite3.connect(path)
    for stmt in SCHEMA:
        conn.execute(stmt)
    conn.execute("INSERT INTO experiments VALUES (1, 'sanad-sft', 'active')")
    for uuid, name, status in runs:
        conn.execute(
            "INSERT INTO runs VALUES (?, ?, ?, 1785211425487, 1785214741196, 1, 'active')",
            (uuid, name, status),
        )
        conn.execute("INSERT INTO params VALUES ('seed', '3407', ?)", (uuid,))
        conn.execute("INSERT INTO params VALUES ('lora_r', '16', ?)", (uuid,))
        # a parameter outside PARAM_KEYS — MLflow logs 300+ of these and they must not land
        conn.execute("INSERT INTO params VALUES ('ddp_timeout', '1800', ?)", (uuid,))
        conn.execute(
            "INSERT INTO latest_metrics VALUES ('peak_vram_gb', 15.594489344, 0, ?, 0, 0)", (uuid,)
        )
        for step, value in ((10, 2.6732), (20, 1.9743)):
            conn.execute("INSERT INTO metrics VALUES ('loss', ?, 0, ?, ?, 0)", (value, uuid, step))
        # a NaN sample: mlflow records these with is_nan=1 and a placeholder value
        conn.execute("INSERT INTO metrics VALUES ('loss', 0.0, 0, ?, 30, 1)", (uuid,))
    conn.commit()
    conn.close()


def _bytes(report: dict[str, object]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def test_export_is_byte_deterministic(tmp_path: Path) -> None:
    db = tmp_path / "mlflow.db"
    _store(db)
    first = _bytes(build_report(db, "b8ccaafc"))
    second = _bytes(build_report(db, "b8ccaafc"))
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_ambiguous_run_prefix_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "mlflow.db"
    _store(db, runs=((RUN, "shad-242", "FINISHED"), ("b8ccaafc0000", "cod-256", "FAILED")))
    with pytest.raises(ExportError, match="ambiguous"):
        build_report(db, "b8ccaafc")


def test_missing_run_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "mlflow.db"
    _store(db)
    with pytest.raises(ExportError, match="no active run"):
        build_report(db, "deadbeef")


def test_report_keeps_pinned_params_and_drops_the_rest(tmp_path: Path) -> None:
    db = tmp_path / "mlflow.db"
    _store(db)
    report = build_report(db, "b8ccaafc")
    assert report["params"] == {"seed": "3407", "lora_r": "16"}
    assert report["metrics"]["peak_vram_gb"] == 15.594489344
    # NaN samples are excluded, so a diverged step cannot masquerade as a loss value
    assert [p["step"] for p in report["metric_history"]["loss"]] == [10, 20]
    # cost is stated as the $0 it was, with the cloud-equivalent estimate explained, not exported
    assert report["cost"]["usd_actual"] == 0.0
    assert "cost_usd" not in report["metrics"]
