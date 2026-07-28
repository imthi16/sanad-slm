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
import re
import sys
import time
from pathlib import Path
from typing import Any

import structlog
import yaml

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "registry"))


#: A pinned revision is a full 40-character commit sha and nothing else. Matching only the
#: placeholder let `revision: main` — or a tag, which upstream can move — pass the gate, so the
#: shape is checked rather than one known-bad value (prime directive 4).
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def load_config(path: Path) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    revision = str(cfg.get("revision", ""))
    if not _COMMIT_SHA.match(revision):
        raise SystemExit(
            f"config revision {revision!r} is not a 40-char commit sha — pin the exact HF "
            "revision before training (prime directive 4: reproducibility over vibes). "
            "Branches and tags move; a sha does not."
        )
    return cfg


def config_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: PEFT understands `target_modules="all-linear"`, but Unsloth's *text* path never lets the string
#: reach PEFT: `llama.py` does `list(target_modules)` and `for module in target_modules`, so the
#: shorthand arrives as its own characters and injection dies with
#: `Target modules {'n','-','r','a','l','i','e'} not found in the base model`. (Unsloth handles the
#: shorthand only in `vision.py`, which `FastLanguageModel` does not use.) So expand it here.
ALL_LINEAR = "all-linear"

#: Excluded from the expansion exactly as PEFT's own shorthand excludes them. Adapting the
#: embedding or the output head changes the tokenizer contract rather than task behaviour, and on
#: Qwen3 the two are tied — adapting one silently perturbs the other.
_NEVER_ADAPT = frozenset({"embed_tokens", "lm_head"})


def _is_linear(module: object) -> bool:
    """Duck-typed so this file stays importable (and testable) without torch installed.

    Matching the class-name across the MRO catches `nn.Linear`, its subclasses, and
    bitsandbytes' `Linear4bit`/`Linear8bitLt` — which is the form every layer takes under
    `load_in_4bit: true`.
    """
    return any("Linear" in klass.__name__ for klass in type(module).__mro__)


def resolve_target_modules(spec: Any, model: Any) -> list[str]:
    """Turn the config's `target_modules` into the explicit list Unsloth requires.

    A list passes through untouched. `all-linear` is expanded by introspecting the loaded model,
    so it stays correct if the base architecture changes, and the resolved list is logged to
    MLflow — an explicit record of which modules actually received adapters beats a shorthand
    nobody can reconstruct from the run later (prime directive 4).
    """
    if not isinstance(spec, str):
        return [str(m) for m in spec]
    if spec != ALL_LINEAR:
        raise SystemExit(
            f"target_modules {spec!r} is a bare string. Unsloth's text path iterates strings "
            f"character-by-character, so only the {ALL_LINEAR!r} shorthand (expanded here) or an "
            "explicit list of module names will work."
        )

    found = {
        name.rsplit(".", 1)[-1]
        for name, module in model.named_modules()
        if _is_linear(module) and name.rsplit(".", 1)[-1] not in _NEVER_ADAPT
    }
    if not found:
        raise SystemExit(
            f"{ALL_LINEAR!r} matched no linear modules in the loaded model — refusing to train an "
            "adapter that would touch nothing."
        )
    return sorted(found)


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

    # Unsloth FIRST, before trl/transformers/peft — it patches them at import time by rebinding
    # `trl.SFTTrainer` and `trl.SFTConfig` to its own subclasses. A name bound from trl *before*
    # that keeps pointing at the unpatched class, so the run drives an Unsloth-patched model and
    # tokenizer through stock TRL. That mismatch is what raised
    # `eos_token ('<EOS_TOKEN>') is not found in the vocabulary` on 2026-07-28: Unsloth's trainer
    # resolves that sentinel, stock TRL validates it literally and rejects it (ADR-0007).
    # Unsloth prints a UserWarning about this; it is load-bearing, not cosmetic.
    import unsloth  # noqa: F401  # isort: skip  — import for side effects, order matters

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
        target_modules = resolve_target_modules(lora["target_modules"], model)
        log.info("target_modules resolved", spec=lora["target_modules"], modules=target_modules)
        mlflow.log_param("target_modules", ",".join(target_modules))

        model = FastLanguageModel.get_peft_model(
            model,
            r=lora["r"],
            lora_alpha=lora["alpha"],
            lora_dropout=lora["dropout"],
            use_dora=lora["use_dora"],
            target_modules=target_modules,
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
