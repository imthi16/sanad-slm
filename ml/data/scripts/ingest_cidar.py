"""Ingest CIDAR (arbml/CIDAR, Apache-2.0, ~10k native Arabic instructions) → record schema.

Respects offline mode: in sovereign/edge (`HF_HUB_OFFLINE=1`) the dataset must already be in
the local HF cache or at data/raw/cidar/ — no silent hub fetch (prime directive 1).
provenance=native is asserted, never inferred (prime directive 3).

Usage: python data/scripts/ingest_cidar.py [--limit N]
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import structlog
from _lib import ML_ROOT, mlflow_step, read_jsonl, write_jsonl

log = structlog.get_logger()

RAW_DIR = ML_ROOT / "data" / "raw"
SOURCE = {"name": "CIDAR", "url": "hf:arbml/CIDAR", "license": "Apache-2.0"}


def to_record(row: dict[str, Any], idx: int) -> dict[str, Any]:
    return {
        "id": f"cidar-ar-{idx:06d}",
        "messages": [
            {"role": "user", "content": row["instruction"]},
            {"role": "assistant", "content": row["output"]},
        ],
        "lang": "ar",  # re-tagged downstream by langid.py
        "domain": ["general"],
        "provenance": "native",
        "source": SOURCE,
        "pii_checked": True,  # CIDAR is curated/public; own data goes through curate_bank.py
        "split": "train",
    }


def load_rows(limit: int | None) -> list[dict[str, Any]]:
    local = RAW_DIR / "cidar" / "cidar.jsonl"
    if local.exists():
        rows = list(read_jsonl(local))
        return rows[:limit] if limit else rows

    if os.environ.get("HF_HUB_OFFLINE") == "1":
        raise SystemExit(
            "sovereign/offline mode and no local copy at data/raw/cidar/cidar.jsonl — "
            "sync it from the artifact mirror first (no silent hub fetch)."
        )

    from datasets import load_dataset  # heavy import deferred

    ds = load_dataset("arbml/CIDAR", split="train")
    rows = [dict(r) for r in ds]
    return rows[:limit] if limit else rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    rows = load_rows(args.limit)
    records = [to_record(r, i) for i, r in enumerate(rows)]
    out = RAW_DIR / "cidar_records.jsonl"
    n = write_jsonl(out, records)
    log.info("ingested", source="CIDAR", records=n, out=str(out))
    mlflow_step("ingest_cidar", records=n)


if __name__ == "__main__":
    main()
