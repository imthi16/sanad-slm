"""AWQ W4A16 via llm-compressor → compressed-tensors checkpoint (vLLM loads natively).

AutoAWQ is archived — do not add it (§3.1). The calibration set MUST be ≥40% Arabic:
English-only calibration is the single most common silent failure mode for Arabic quality
(§5.3) — this script refuses to run below the threshold.

Usage:
    uv run python quantize/awq.py --model out/merged-bf16 \
        --recipe configs/quant/awq-w4a16.yaml \
        --calib data/processed/calib_bilingual_512.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog
import yaml

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "data" / "scripts"))


def check_bilingual(calib_path: Path, min_arabic_ratio: float) -> float:
    from _lib import read_jsonl, script_ratios

    texts = []
    for rec in read_jsonl(calib_path):
        if "messages" in rec:
            texts.append("\n".join(m["content"] for m in rec["messages"]))
        else:
            texts.append(rec.get("text", ""))
    if not texts:
        raise SystemExit(f"calibration file {calib_path} is empty")

    ar_chars = sum(script_ratios(t)[0] * max(len(t), 1) for t in texts)
    total = sum(max(len(t), 1) for t in texts)
    ratio = ar_chars / total
    if ratio < min_arabic_ratio:
        raise SystemExit(
            f"calibration set is only {ratio:.0%} Arabic (< {min_arabic_ratio:.0%}) — "
            "English-heavy calibration silently degrades Arabic; fix the calib set (§5.3)"
        )
    log.info("calib_ok", arabic_ratio=round(ratio, 3), samples=len(texts))
    return ratio


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--recipe", type=Path, default=ML_ROOT / "configs/quant/awq-w4a16.yaml")
    ap.add_argument("--calib", type=Path, required=True)
    args = ap.parse_args()

    recipe_cfg = yaml.safe_load(args.recipe.read_text(encoding="utf-8"))
    calib_cfg = recipe_cfg["calibration"]
    out_dir = ML_ROOT / recipe_cfg["output_dir"]

    check_bilingual(args.calib, calib_cfg["min_arabic_ratio"])

    from datasets import load_dataset
    from llmcompressor import oneshot
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(args.model))
    ds = load_dataset("json", data_files=str(args.calib), split="train")
    ds = ds.select(range(min(calib_cfg["num_samples"], len(ds))))

    def preprocess(row: dict) -> dict:  # type: ignore[type-arg]
        if row.get("messages"):
            text = tokenizer.apply_chat_template(row["messages"], tokenize=False)
        else:
            text = row.get("text", "")
        return {"text": text}

    ds = ds.map(preprocess)

    oneshot(
        model=str(args.model),
        dataset=ds,
        recipe=yaml.safe_dump(recipe_cfg["recipe"]),
        output_dir=str(out_dir),
        max_seq_length=calib_cfg["max_seq_len"],
        num_calibration_samples=calib_cfg["num_samples"],
    )
    log.info("awq_done", out=str(out_dir), note="run `just ppl-gate` before release")


if __name__ == "__main__":
    main()
