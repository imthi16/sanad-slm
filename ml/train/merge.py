"""Standalone adapter → merged-bf16 merge (when re-merging without retraining).

sft.py already saves a merged model; this exists for merging a previously trained adapter
onto a (re-verified) base — e.g. after an Unsloth version bump. Writes the same lineage
manifest as sft.py so registry/push.py accepts the output.

Usage: uv run python train/merge.py --config configs/train/qwen3-4b-qlora-dora.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog
import yaml

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "registry"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config", type=Path, default=ML_ROOT / "configs/train/qwen3-4b-qlora-dora.yaml"
    )
    ap.add_argument("--adapter", type=Path, default=None, help="override adapter dir")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    adapter_dir = args.adapter or ML_ROOT / cfg["outputs"]["adapter_dir"]
    merged_dir = ML_ROOT / cfg["outputs"]["merged_dir"]

    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(adapter_dir),
        max_seq_length=cfg["max_seq_len"],
        load_in_4bit=cfg["load_in_4bit"],
        dtype=None,
    )
    model.save_pretrained_merged(str(merged_dir), tokenizer, save_method="merged_16bit")

    from artifact_manifest import write_lineage

    write_lineage(
        merged_dir,
        base_model=cfg["base_model"],
        base_revision=cfg["revision"],
        train_config=args.config,
        mlflow_run_id=None,
    )
    log.info("merged", adapter=str(adapter_dir), merged=str(merged_dir))


if __name__ == "__main__":
    main()
