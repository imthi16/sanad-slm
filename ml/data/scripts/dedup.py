"""Near-duplicate removal: MinHash LSH, drop at Jaccard ≥ 0.85 (§5.1).

Keys are aggressively normalized (`_lib.dedup_key`) so Arabic orthographic variants collide;
stored text is untouched. Deterministic: shards are processed in sorted order, first record
of a duplicate cluster wins. Idempotent by construction.

Usage: python data/scripts/dedup.py <dir>
"""

from __future__ import annotations

import argparse
from pathlib import Path

import structlog
from _lib import dedup_key, mlflow_step, read_jsonl, record_text, write_jsonl
from datasketch import MinHash, MinHashLSH

log = structlog.get_logger()

JACCARD_THRESHOLD = 0.85
NUM_PERM = 128
SHINGLE = 5  # character shingles work for both scripts (word shingles under-fire on Arabic)


def minhash(text: str) -> MinHash:
    mh = MinHash(num_perm=NUM_PERM, seed=3407)
    key = dedup_key(text)
    for i in range(max(1, len(key) - SHINGLE + 1)):
        mh.update(key[i : i + SHINGLE].encode("utf-8"))
    return mh


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir", type=Path)
    args = ap.parse_args()

    lsh = MinHashLSH(threshold=JACCARD_THRESHOLD, num_perm=NUM_PERM)
    kept_total = dropped_total = 0

    for shard in sorted(args.dir.glob("*.jsonl")):
        kept = []
        for rec in read_jsonl(shard):
            mh = minhash(record_text(rec))
            if lsh.query(mh):
                dropped_total += 1
                log.debug("dup_dropped", id=rec.get("id"))
                continue
            lsh.insert(rec["id"], mh)
            kept.append(rec)
        write_jsonl(shard, kept)
        kept_total += len(kept)
        log.info("dedup", file=shard.name, kept=len(kept))

    log.info("dedup_done", kept=kept_total, dropped=dropped_total)
    mlflow_step("dedup", kept=kept_total, dropped=dropped_total, threshold=JACCARD_THRESHOLD)


if __name__ == "__main__":
    main()
