"""Build the quantization calibration sets and the PPL held-out shard (§5.3).

Three artifacts the P3 path reads and nothing produced — `ppl_gate.py`'s own error message even
says "generate it in `just data`":

* `calib_bilingual_512.jsonl` — AWQ calibration for `quantize/awq.py`
* `calib_bilingual.txt`       — importance-matrix text for `quantize/gguf.sh`
* `ppl_heldout_bilingual.jsonl` — the fixed shard `quantize/ppl_gate.py` scores

**Calibration comes from train, the PPL holdout comes from val.** Perplexity measured on data the
quantizer was calibrated on is flattered, and the whole point of the gate is to catch quantization
quietly wrecking Arabic — so the two sets must not overlap. Drawing them from shards that are
already disjoint makes that structural rather than a promise, and the overlap is asserted anyway.

**The Arabic target is measured in characters, not records.** `awq.py` gates on the char-weighted
Arabic ratio, so picking half the records Arabic can still land under the floor when the English
records are longer. This selects until the char ratio itself clears the target, and reports what it
achieved.

Sample count and the ratio floor are read from `configs/quant/awq-w4a16.yaml`, so the generator
cannot drift away from the gate that checks its output.

Usage: python data/scripts/calib.py [--num-samples N] [--heldout N]
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

import structlog
import yaml
from _lib import ML_ROOT, mlflow_step, read_jsonl, record_text, script_ratios, write_jsonl

log = structlog.get_logger()

PROCESSED = ML_ROOT / "data" / "processed"
SPLITS = PROCESSED / "splits"
AWQ_RECIPE = ML_ROOT / "configs" / "quant" / "awq-w4a16.yaml"

CALIB_JSONL = PROCESSED / "calib_bilingual_512.jsonl"
CALIB_TXT = PROCESSED / "calib_bilingual.txt"
PPL_HELDOUT = PROCESSED / "ppl_heldout_bilingual.jsonl"

DEFAULT_HELDOUT = 256
#: aim above the gate's floor — landing exactly on it leaves no room for a corpus shift
RATIO_HEADROOM = 0.10
SEED = 3407


def arabic_char_ratio(records: list[dict[str, Any]]) -> float:
    """Char-weighted Arabic share, measured exactly the way awq.py's gate measures it."""
    ar = 0.0
    total = 0
    for rec in records:
        text = record_text(rec)
        ar += script_ratios(text)[0] * max(len(text), 1)
        total += max(len(text), 1)
    return ar / total if total else 0.0


def pick_bilingual(
    pool: list[dict[str, Any]], count: int, target_ratio: float, seed: int
) -> list[dict[str, Any]]:
    """Take `count` records whose char-weighted Arabic share reaches `target_ratio`.

    Arabic-leading records are added while the running ratio sits below target and non-Arabic ones
    when it is above, so the result is bilingual by construction rather than by luck — an
    all-Arabic calibration set would be as wrong as an all-English one, just in the other
    direction (§5.3 wants bilingual, not Arabic-only).
    """
    rng = random.Random(seed)
    arabic = [r for r in pool if str(r.get("lang")) in ("ar", "mixed")]
    other = [r for r in pool if str(r.get("lang")) not in ("ar", "mixed")]
    rng.shuffle(arabic)
    rng.shuffle(other)

    chosen: list[dict[str, Any]] = []
    ar_chars = 0.0
    total_chars = 0
    while len(chosen) < count and (arabic or other):
        running = ar_chars / total_chars if total_chars else 0.0
        take_arabic = (running < target_ratio and arabic) or not other
        rec = arabic.pop() if take_arabic else other.pop()
        text = record_text(rec)
        ar_chars += script_ratios(text)[0] * max(len(text), 1)
        total_chars += max(len(text), 1)
        chosen.append(rec)
    return chosen


def load_shard(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(
            f"{label} shard missing: {path.relative_to(ML_ROOT)} — run `just data` first "
            "(the split step produces it)"
        )
    records = list(read_jsonl(path))
    if not records:
        raise SystemExit(f"{label} shard is empty: {path.relative_to(ML_ROOT)}")
    return records


def main() -> None:
    recipe = yaml.safe_load(AWQ_RECIPE.read_text(encoding="utf-8"))
    calib_cfg = recipe["calibration"]
    floor = float(calib_cfg["min_arabic_ratio"])

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--num-samples", type=int, default=int(calib_cfg["num_samples"]))
    ap.add_argument("--heldout", type=int, default=DEFAULT_HELDOUT)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    train = load_shard(SPLITS / "train.jsonl", "train")
    val = load_shard(SPLITS / "val.jsonl", "val")

    target = min(floor + RATIO_HEADROOM, 0.9)
    calib = pick_bilingual(train, args.num_samples, target, args.seed)
    heldout = pick_bilingual(val, args.heldout, target, args.seed + 1)

    calib_ratio = arabic_char_ratio(calib)
    heldout_ratio = arabic_char_ratio(heldout)

    if calib_ratio < floor:
        raise SystemExit(
            f"calibration set reached only {calib_ratio:.0%} Arabic characters, below the "
            f"{floor:.0%} floor awq.py enforces. The corpus is too English-heavy for a "
            f"{args.num_samples}-sample set — curate more Arabic records (§5.1 targets 60% AR)."
        )

    # Structural, but assert it: a PPL gate scored on calibration data cannot detect the failure
    # it exists to catch.
    overlap = {r["id"] for r in calib} & {r["id"] for r in heldout}
    if overlap:
        raise SystemExit(f"calibration and PPL holdout share {len(overlap)} record(s): {overlap}")

    n_calib = write_jsonl(CALIB_JSONL, calib)
    n_heldout = write_jsonl(PPL_HELDOUT, heldout)
    CALIB_TXT.parent.mkdir(parents=True, exist_ok=True)
    CALIB_TXT.write_text(
        "\n\n".join(record_text(r) for r in calib) + "\n",
        encoding="utf-8",
    )

    log.info(
        "calib_built",
        calib=n_calib,
        calib_arabic_chars=round(calib_ratio, 3),
        floor=floor,
        imatrix_txt_kb=round(CALIB_TXT.stat().st_size / 1024, 1),
        ppl_heldout=n_heldout,
        heldout_arabic_chars=round(heldout_ratio, 3),
        disjoint=True,
    )
    mlflow_step(
        "calib",
        calib=n_calib,
        calib_arabic_ratio=round(calib_ratio, 4),
        ppl_heldout=n_heldout,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
