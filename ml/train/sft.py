"""Unsloth QLoRA + DoRA SFT on Qwen3-4B (CLAUDE.md §5.2).

Responsibilities: load config → Unsloth FastLanguageModel → Qwen3 chat template with
enable_thinking=False → TRL SFTTrainer → log loss/LR/VRAM/cost to MLflow → save adapter AND
merged bf16 → registry/manifest.py writes lineage.

Acceptance: completes on a single 24 GB GPU with <16 GB peak VRAM; cost logged (< $50 budget).

Usage: uv run python train/sft.py --config configs/train/qwen3-4b-qlora-dora.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import structlog
import yaml

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "registry"))


def load_config(path: Path) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "<pin-hf-commit-sha>" in str(cfg.get("revision", "")):
        raise SystemExit(
            "config revision is unpinned — pin the exact HF commit sha before training "
            "(prime directive 4: reproducibility over vibes)"
        )
    return cfg


def config_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak_vram_gb() -> float:
    import torch

    return torch.cuda.max_memory_allocated() / 1e9 if torch.cuda.is_available() else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config", type=Path, default=ML_ROOT / "configs/train/qwen3-4b-qlora-dora.yaml"
    )
    ap.add_argument(
        "--gpu-usd-per-hour", type=float, default=float(os.environ.get("SANAD_GPU_USD_HR", "0.60"))
    )
    args = ap.parse_args()

    cfg = load_config(args.config)
    lora, tr, out = cfg["lora"], cfg["train"], cfg["outputs"]

    import mlflow
    import torch
    from chat_template import assert_non_thinking, format_for_sft, formatting_func
    from datasets import load_dataset
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastLanguageModel

    torch.manual_seed(cfg["seed"])
    mlflow.set_experiment(cfg["logging"]["mlflow_experiment"])

    with mlflow.start_run() as run:
        mlflow.log_params(
            {
                "base_model": cfg["base_model"],
                "revision": cfg["revision"],
                "seed": cfg["seed"],
                "max_seq_len": cfg["max_seq_len"],
                "lora_r": lora["r"],
                "use_dora": lora["use_dora"],
                "epochs": tr["epochs"],
                "lr": tr["lr"],
                "effective_batch": tr["per_device_batch"] * tr["grad_accum"],
                "config_sha256": config_sha(args.config),
            }
        )

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=cfg["base_model"],
            revision=cfg["revision"],
            max_seq_length=cfg["max_seq_len"],
            load_in_4bit=cfg["load_in_4bit"],  # NF4 via bitsandbytes
            dtype=None,  # auto bf16 on Ampere+
        )
        model = FastLanguageModel.get_peft_model(
            model,
            r=lora["r"],
            lora_alpha=lora["alpha"],
            lora_dropout=lora["dropout"],
            use_dora=lora["use_dora"],
            target_modules=lora["target_modules"],
            random_state=cfg["seed"],
        )

        # sanity: the qwen3 template must render non-thinking
        probe = format_for_sft(
            tokenizer,
            [{"role": "user", "content": "مرحبا"}, {"role": "assistant", "content": "أهلاً"}],
        )
        assert_non_thinking(probe)

        dataset = load_dataset("json", data_files=str(ML_ROOT / cfg["dataset"]), split="train")
        eval_ds = load_dataset("json", data_files=str(ML_ROOT / cfg["eval_holdout"]), split="train")

        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=dataset,
            eval_dataset=eval_ds,
            formatting_func=formatting_func(tokenizer),
            args=SFTConfig(
                output_dir=str(ML_ROOT / "out" / "checkpoints"),
                num_train_epochs=tr["epochs"],
                learning_rate=tr["lr"],
                lr_scheduler_type=tr["scheduler"],
                warmup_ratio=tr["warmup_ratio"],
                per_device_train_batch_size=tr["per_device_batch"],
                gradient_accumulation_steps=tr["grad_accum"],
                packing=tr["packing"],
                bf16=tr["bf16"],
                optim=tr["optim"],
                neftune_noise_alpha=tr["neftune_noise_alpha"],
                max_length=cfg["max_seq_len"],
                logging_steps=cfg["logging"]["log_steps"],
                eval_strategy="epoch",
                save_strategy="epoch",
                seed=cfg["seed"],
                report_to="mlflow",
            ),
        )

        t0 = time.monotonic()
        result = trainer.train()
        hours = (time.monotonic() - t0) / 3600

        vram = peak_vram_gb()
        cost = hours * args.gpu_usd_per_hour
        mlflow.log_metrics(
            {
                "train_loss": result.training_loss,
                "peak_vram_gb": vram,
                "train_hours": hours,
                "cost_usd": cost,
            }
        )
        budget = cfg.get("budget", {})
        if vram > budget.get("max_peak_vram_gb", 16):
            log.error(
                "vram_budget_exceeded", peak_gb=vram, budget_gb=budget.get("max_peak_vram_gb")
            )
        if cost > budget.get("max_cost_usd", 50):
            log.error("cost_budget_exceeded", cost_usd=cost, budget_usd=budget.get("max_cost_usd"))

        # save adapter AND merged bf16
        adapter_dir = ML_ROOT / out["adapter_dir"]
        merged_dir = ML_ROOT / out["merged_dir"]
        model.save_pretrained(str(adapter_dir))
        tokenizer.save_pretrained(str(adapter_dir))
        model.save_pretrained_merged(str(merged_dir), tokenizer, save_method="merged_16bit")

        from artifact_manifest import write_lineage  # registry/artifact_manifest.py

        write_lineage(
            merged_dir,
            base_model=cfg["base_model"],
            base_revision=cfg["revision"],
            train_config=args.config,
            mlflow_run_id=run.info.run_id,
        )
        log.info(
            "sft_done",
            adapter=str(adapter_dir),
            merged=str(merged_dir),
            peak_vram_gb=round(vram, 2),
            cost_usd=round(cost, 2),
        )
        print(json.dumps({"run_id": run.info.run_id, "peak_vram_gb": vram, "cost_usd": cost}))


if __name__ == "__main__":
    main()
