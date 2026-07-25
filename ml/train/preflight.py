"""Check everything a training run needs, before the run starts (`just preflight`).

A QLoRA run on a 4090 takes hours. Every failure below is one that would otherwise surface after
the model has downloaded and the first epoch has begun — or worse, produce a run whose numbers
cannot be compared to anything. Each check prints what to do about it rather than just what is
wrong.

Exit code 0 = safe to start. Non-zero = at least one blocking problem.

Usage: uv run python train/preflight.py [--config configs/train/qwen3-4b-qlora-dora.yaml]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

ML_ROOT = Path(__file__).resolve().parents[1]
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

#: The recipe targets a "single 24 GB GPU" (§0) with peak allocation under 16 GB (§5.2). Those are
#: different numbers: a 16 GB card running a 16 GB peak has no headroom for fragmentation or the
#: merge step, so the card must be meaningfully larger than the budget it has to fit inside.
MIN_GPU_VRAM_GB = 20.0


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, check: str, detail: str) -> None:
        self.rows.append((status, check, detail))

    @property
    def failed(self) -> bool:
        return any(status == FAIL for status, _, _ in self.rows)

    def render(self) -> str:
        icon = {PASS: "✓", WARN: "!", FAIL: "✗"}
        width = max(len(check) for _, check, _ in self.rows)
        lines = [f"  {icon[s]} {c.ljust(width)}  {d}" for s, c, d in self.rows]
        counts = {k: sum(1 for s, _, _ in self.rows if s == k) for k in (PASS, WARN, FAIL)}
        summary = f"{counts[PASS]} passed, {counts[WARN]} warning(s), {counts[FAIL]} blocking"
        return "\n".join(["", *lines, "", f"  {summary}", ""])


def check_gpu(rep: Report, peak_budget_gb: float) -> None:
    if importlib.util.find_spec("torch") is None:
        rep.add(FAIL, "torch", "not installed — run `uv sync --extra train` on the GPU box")
        return
    import torch

    if not torch.cuda.is_available():
        rep.add(
            FAIL,
            "cuda",
            "torch cannot see a GPU — check `nvidia-smi` and that the driver matches this "
            f"torch build (torch {torch.__version__}, cuda {torch.version.cuda})",
        )
        return
    name = torch.cuda.get_device_name(0)
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9
    status = PASS if vram >= MIN_GPU_VRAM_GB else FAIL
    rep.add(
        status,
        "cuda",
        f"{name}, {vram:.1f} GB total (needs ≥ {MIN_GPU_VRAM_GB:.0f} GB to hold a "
        f"{peak_budget_gb:.0f} GB peak with headroom)",
    )
    # bf16 is native on Ada; without it the canonical config's bf16: true is wrong for this box
    if torch.cuda.is_bf16_supported():
        rep.add(PASS, "bf16", "supported natively — canonical config applies unchanged")
    else:
        rep.add(
            FAIL,
            "bf16",
            "not supported — this GPU needs an fp16 config variant (ADR-0004 fallback path)",
        )


def check_packages(rep: Report) -> None:
    for mod, extra in (
        ("unsloth", "train"),
        ("trl", "train"),
        ("peft", "train"),
        ("bitsandbytes", "train"),
        ("datasets", "train"),
        ("mlflow", "base"),
    ):
        if importlib.util.find_spec(mod) is None:
            hint = (
                "already in base deps — reinstall"
                if extra == "base"
                else f"uv sync --extra {extra}"
            )
            rep.add(FAIL, mod, f"missing — {hint}")
        else:
            rep.add(PASS, mod, "installed")


def check_config(rep: Report, cfg_path: Path) -> dict[str, Any]:
    if not cfg_path.exists():
        rep.add(FAIL, "config", f"{cfg_path} not found")
        return {}
    cfg: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    revision = str(cfg.get("revision", ""))
    if _COMMIT_SHA.match(revision):
        rep.add(PASS, "base revision", f"pinned to {revision[:12]}… ({cfg.get('base_model')})")
    else:
        rep.add(
            FAIL,
            "base revision",
            f"{revision!r} is not a 40-char commit sha — a branch or tag would make this run "
            "unreproducible (prime directive 4)",
        )
    return cfg


def check_data(rep: Report, cfg: dict[str, Any]) -> None:
    for key, label in (("dataset", "train shard"), ("eval_holdout", "val shard")):
        rel = cfg.get(key)
        if not rel:
            rep.add(FAIL, label, f"config has no `{key}`")
            continue
        path = ML_ROOT / str(rel)
        if not path.exists():
            rep.add(FAIL, label, f"{rel} missing — run `just data` first")
            continue
        n = sum(1 for _ in path.open(encoding="utf-8"))
        status = PASS if n else FAIL
        rep.add(status, label, f"{rel} — {n} records")


def check_offline_posture(rep: Report) -> None:
    mode = os.environ.get("SANAD_MODE", "dev")
    offline = os.environ.get("HF_HUB_OFFLINE") == "1"
    if mode == "dev":
        rep.add(PASS, "mode", "dev — the base model may be fetched from the hub")
    elif offline:
        rep.add(PASS, "mode", f"{mode} with HF_HUB_OFFLINE=1 — weights must already be cached")
    else:
        rep.add(
            FAIL,
            "mode",
            f"SANAD_MODE={mode} without HF_HUB_OFFLINE=1 — sovereign/edge runs must not be able "
            "to reach the hub (prime directive 1)",
        )
    if os.environ.get("HF_TOKEN") or (Path.home() / ".cache/huggingface/token").exists():
        rep.add(PASS, "hf credentials", "token present — gated assets can be resolved")
    else:
        rep.add(
            WARN,
            "hf credentials",
            "no HF_TOKEN — fine for Qwen3 (ungated), but jais and Llama-3.2 need one (§15)",
        )


def check_disk(rep: Report, min_free_gb: float = 60.0) -> None:
    free = shutil.disk_usage(ML_ROOT).free / 1e9
    status = PASS if free >= min_free_gb else WARN
    rep.add(
        status,
        "disk",
        f"{free:.0f} GB free — base weights, adapter and merged bf16 need roughly "
        f"{min_free_gb:.0f} GB together",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config", type=Path, default=ML_ROOT / "configs/train/qwen3-4b-qlora-dora.yaml"
    )
    args = ap.parse_args()

    rep = Report()
    cfg = check_config(rep, args.config)
    peak_budget = float((cfg.get("budget") or {}).get("max_peak_vram_gb", 16))
    check_gpu(rep, peak_budget)
    check_packages(rep)
    check_data(rep, cfg)
    check_offline_posture(rep)
    check_disk(rep)

    shown = args.config.name if args.config.is_absolute() else args.config
    print(f"preflight — {shown}")
    print(rep.render())
    if rep.failed:
        print("  Not safe to start. Fix the ✗ rows above, then rerun `just preflight`.\n")
        sys.exit(1)
    print("  Ready — `just train` is safe to start.\n")


if __name__ == "__main__":
    main()
