"""Quantization quality gate (§5.3, §11) — release-blocking.

Perplexity on a fixed bilingual held-out shard, quantized vs bf16:
  fail if ΔPPL > 3% (AWQ / compressed-tensors) or > 5% (GGUF Q4_K_M),
  or if ArabicMMLU drops > 1.0 pt (read from lm-eval reports when present).

Rationale: the single most common silent failure is English-calibrated quantization quietly
wrecking Arabic — so PPL is also reported per-language, not just pooled.

Usage: uv run python quantize/ppl_gate.py --model out/awq-w4a16 [--baseline out/merged-bf16]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import structlog

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "data" / "scripts"))

HELDOUT = ML_ROOT / "data" / "processed" / "ppl_heldout_bilingual.jsonl"
REPORTS = ML_ROOT / "evals" / "reports"

THRESHOLDS = {"awq": 0.03, "gguf": 0.05}
MAX_ARABICMMLU_DROP = 1.0


def kind_of(model_path: Path) -> str:
    return "gguf" if model_path.suffix == ".gguf" else "awq"


def ppl_hf(model_path: Path, texts: list[str]) -> float:
    """PPL via transformers for HF/compressed-tensors checkpoints."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(model_path))
    model = AutoModelForCausalLM.from_pretrained(
        str(model_path), torch_dtype="auto", device_map="auto"
    )
    model.eval()
    nll, count = 0.0, 0
    with torch.no_grad():
        for text in texts:
            enc = tok(text, return_tensors="pt", truncation=True, max_length=2048).to(model.device)
            out = model(**enc, labels=enc["input_ids"])
            n = enc["input_ids"].numel()
            nll += out.loss.item() * n
            count += n
    return float(torch.exp(torch.tensor(nll / count)))


def ppl_gguf(model_path: Path, texts: list[str]) -> float:
    """PPL via llama.cpp llama-perplexity on the same shard."""
    import subprocess
    import tempfile

    llama_dir = Path(os.environ.get("LLAMA_CPP_DIR", ML_ROOT / "out" / "llama.cpp"))
    binary = llama_dir / "build" / "bin" / "llama-perplexity"
    if not binary.exists():
        raise SystemExit(f"llama-perplexity not built at {binary} — run quantize/gguf.sh first")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write("\n\n".join(texts))
        tmp = fh.name
    out = subprocess.run(
        [str(binary), "-m", str(model_path), "-f", tmp, "--ppl-stride", "0"],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in reversed(out.stderr.splitlines() + out.stdout.splitlines()):
        if "PPL =" in line:
            return float(line.split("PPL =")[1].split()[0].rstrip(","))
    raise SystemExit("could not parse PPL from llama-perplexity output")


def arabicmmlu_drop() -> float | None:
    """Δ(base − quantized) ArabicMMLU from lm-eval reports, if both exist."""
    scores: dict[str, float] = {}
    for report in REPORTS.glob("**/results*.json"):
        data = json.loads(report.read_text(encoding="utf-8"))
        acc = data.get("results", {}).get("arabicmmlu", {}).get("acc,none")
        if acc is not None:
            scores[report.parent.name] = float(acc) * 100
    base = next((v for k, v in scores.items() if "bf16" in k or "base" in k), None)
    quant = next((v for k, v in scores.items() if "awq" in k or "gguf" in k or "q4" in k), None)
    if base is None or quant is None:
        return None
    return base - quant


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, required=True, help="quantized model (dir or .gguf)")
    ap.add_argument("--baseline", type=Path, default=ML_ROOT / "out" / "merged-bf16")
    args = ap.parse_args()

    from _lib import read_jsonl, script_ratios

    if not HELDOUT.exists():
        raise SystemExit(f"fixed held-out shard missing: {HELDOUT} — generate it in `just data`")

    records = list(read_jsonl(HELDOUT))
    texts = ["\n".join(m["content"] for m in r["messages"]) for r in records]
    ar_texts = [t for t in texts if script_ratios(t)[0] > 0.5]
    en_texts = [t for t in texts if script_ratios(t)[0] <= 0.5]

    kind = kind_of(args.model)
    threshold = THRESHOLDS[kind]
    quant_fn = ppl_gguf if kind == "gguf" else ppl_hf

    results = {}
    for label, subset in (("pooled", texts), ("ar", ar_texts), ("en", en_texts)):
        base_ppl = ppl_hf(args.baseline, subset)
        quant_ppl = quant_fn(args.model, subset)
        delta = (quant_ppl - base_ppl) / base_ppl
        results[label] = {"base": base_ppl, "quant": quant_ppl, "delta": delta}
        log.info(
            "ppl",
            subset=label,
            base=round(base_ppl, 3),
            quant=round(quant_ppl, 3),
            delta_pct=round(delta * 100, 2),
        )

    report = {"model": str(args.model), "kind": kind, "threshold": threshold, "ppl": results}
    failures = [
        f"{label}: ΔPPL {r['delta']:.1%} > {threshold:.0%}"
        for label, r in results.items()
        if r["delta"] > threshold
    ]
    drop = arabicmmlu_drop()
    if drop is not None:
        report["arabicmmlu_drop_pts"] = drop
        if drop > MAX_ARABICMMLU_DROP:
            failures.append(f"ArabicMMLU dropped {drop:.2f} pts > {MAX_ARABICMMLU_DROP}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"ppl_gate_{args.model.name}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if failures:
        for f in failures:
            log.error("ppl_gate_fail", reason=f)
        raise SystemExit(f"ppl-gate FAILED ({len(failures)} violation(s)) — release blocked")
    log.info("ppl_gate_ok", report=str(out))


if __name__ == "__main__":
    main()
