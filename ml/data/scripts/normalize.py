"""Unicode NFC normalization pass (idempotent).

Raw text is preserved for SFT — only canonical NFC composition is applied to stored content.
CAMeL-style aggressive normalization exists solely in `_lib.dedup_key` for dedup/lang-id keys.

Usage: python data/scripts/normalize.py <in_dir> <out_dir>
"""

from __future__ import annotations

import argparse
from pathlib import Path

import structlog
from _lib import mlflow_step, nfc, read_jsonl, write_jsonl

log = structlog.get_logger()


def normalize_record(rec: dict) -> dict:  # type: ignore[type-arg]
    rec = dict(rec)
    rec["messages"] = [{**m, "content": nfc(m["content"])} for m in rec["messages"]]
    return rec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("in_dir", type=Path)
    ap.add_argument("out_dir", type=Path)
    args = ap.parse_args()

    total = 0
    for src in sorted(args.in_dir.glob("*.jsonl")):
        records = [normalize_record(r) for r in read_jsonl(src)]
        n = write_jsonl(args.out_dir / src.name, records)
        total += n
        log.info("normalized", file=src.name, records=n)

    mlflow_step("normalize", in_dir=str(args.in_dir), out_dir=str(args.out_dir), records=total)


if __name__ == "__main__":
    main()
