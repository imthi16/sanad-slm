"""Split the curated corpus into train/val shards (§5.2 `dataset` + `eval_holdout`).

`train/sft.py` loads `data/processed/splits/train.jsonl` and `val.jsonl`; nothing produced them,
so `just data` followed by `just train` died on a missing file. This is that step.

Two properties matter more than the split itself:

* **Deterministic.** Records are ordered by id and shuffled with a seeded Random, so the same
  corpus always yields the same split. A val set that moves between runs makes two training runs
  incomparable, which defeats the point of pinning everything else (prime directive 4).
* **Stratified by (lang, provenance).** Held-out loss is only meaningful if val mirrors train:
  an unstratified sample of a 60/30/10 ar/en/mixed corpus can under-represent code-switching badly
  enough that the curve says nothing about the case we care about most.

Splits are written to a *subdirectory* on purpose. `normalize`, `langid`, `dedup` and `manifest`
all glob `data/processed/*.jsonl` non-recursively, so keeping the split files out of that glob
stops them being re-processed on a second run and double-counted in MANIFEST.yaml.

Usage: python data/scripts/split.py [--val-fraction 0.05] [--seed 3407]
"""

from __future__ import annotations

import argparse
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import structlog
from _lib import ML_ROOT, mlflow_step, read_jsonl, validate_records, write_jsonl

log = structlog.get_logger()

PROCESSED = ML_ROOT / "data" / "processed"
SPLITS_DIR = PROCESSED / "splits"
#: matches `seed:` in configs/train/qwen3-4b-qlora-dora.yaml — one seed for the whole run
DEFAULT_SEED = 3407
DEFAULT_VAL_FRACTION = 0.05
#: below this a held-out loss curve is noise; better to fail loudly than to report it
MIN_VAL_RECORDS = 20


def stratum(rec: dict[str, Any]) -> tuple[str, str]:
    return str(rec.get("lang", "?")), str(rec.get("provenance", "?"))


def load_corpus(processed: Path) -> list[dict[str, Any]]:
    """Every source shard, ordered by id so the input to the shuffle is itself deterministic."""
    records: list[dict[str, Any]] = []
    for shard in sorted(processed.glob("*.jsonl")):
        records.extend(read_jsonl(shard))
    records.sort(key=lambda r: str(r.get("id", "")))
    return records


def assign(
    records: list[dict[str, Any]], val_fraction: float, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition into (train, val), stratified by (lang, provenance) and seeded."""
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        buckets[stratum(rec)].append(rec)

    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for key in sorted(buckets):
        group = buckets[key]
        random.Random(f"{seed}:{key}").shuffle(group)
        # round rather than floor: a 12-record stratum at 5% should still contribute, and a
        # stratum of 1 stays in train rather than becoming an unpaired val record
        take = round(len(group) * val_fraction) if len(group) > 1 else 0
        for rec in group[:take]:
            val.append({**rec, "split": "val"})
        for rec in group[take:]:
            train.append({**rec, "split": "train"})
    return train, val


def summarise(records: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(f"{lang}/{prov}" for lang, prov in map(stratum, records)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed-dir", type=Path, default=PROCESSED)
    ap.add_argument("--out-dir", type=Path, default=SPLITS_DIR)
    ap.add_argument("--val-fraction", type=float, default=DEFAULT_VAL_FRACTION)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument(
        "--min-val",
        type=int,
        default=MIN_VAL_RECORDS,
        help="fail below this many val records (0 disables the check)",
    )
    args = ap.parse_args()

    if not 0.0 < args.val_fraction < 1.0:
        raise SystemExit(f"--val-fraction must be between 0 and 1, got {args.val_fraction}")

    records = load_corpus(args.processed_dir)
    if not records:
        raise SystemExit(
            f"no records in {args.processed_dir} — run `just data` first "
            "(ingest → normalize → langid → dedup) before splitting"
        )

    # the schema is the contract every downstream stage assumes; check it before writing
    validate_records(records)
    train, val = assign(records, args.val_fraction, args.seed)

    if args.min_val and len(val) < args.min_val:
        raise SystemExit(
            f"only {len(val)} val records from {len(records)} total — a held-out loss curve on "
            f"that is noise. Curate more data, or lower --min-val deliberately."
        )

    n_train = write_jsonl(args.out_dir / "train.jsonl", train)
    n_val = write_jsonl(args.out_dir / "val.jsonl", val)

    log.info(
        "split_done",
        train=n_train,
        val=n_val,
        val_fraction_actual=round(n_val / len(records), 4),
        seed=args.seed,
        strata=len(set(map(stratum, records))),
        train_strata=summarise(train),
        val_strata=summarise(val),
    )
    mlflow_step("split", train=n_train, val=n_val, seed=args.seed, fraction=args.val_fraction)


if __name__ == "__main__":
    main()
