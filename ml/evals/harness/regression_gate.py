"""eval.yml regression gate (§9.5, §11) — red unless:

  domain eval:  fine-tuned ≥ base + 5.0 pts
  ArabicMMLU:   fine-tuned ≥ base − 1.0 pt   (no catastrophic forgetting)

Reads lm-eval + domain reports for the given run id and exits non-zero on violation.
Judge-based claims additionally require the human-validation κ to be present (directive 5) —
checked when a judge report exists for the run.

Usage: uv run python evals/harness/regression_gate.py --run-id <id> \
           [--min-domain-delta 5.0] [--max-arabicmmlu-drop 1.0]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import structlog

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[2]
REPORTS = ML_ROOT / "evals" / "reports"


def find_metric(run_dir: Path, model_hint: str, task: str) -> float | None:
    for report in run_dir.glob(f"*{model_hint}*/results*.json"):
        data = json.loads(report.read_text(encoding="utf-8"))
        res = data.get("results", {}).get(task, {})
        for key in ("acc,none", "acc_norm,none", "exact_match,none"):
            if key in res:
                return float(res[key]) * 100
    return None


def domain_score(run_dir: Path, model_hint: str) -> float | None:
    f = run_dir / f"domain_{model_hint}.json"
    if not f.exists():
        return None
    return float(json.loads(f.read_text(encoding="utf-8"))["aggregate_score"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--min-domain-delta", type=float, default=5.0)
    ap.add_argument("--max-arabicmmlu-drop", type=float, default=1.0)
    args = ap.parse_args()

    run_dir = REPORTS / args.run_id
    if not run_dir.exists():
        raise SystemExit(f"no reports at {run_dir}")

    failures: list[str] = []

    base_mmlu = find_metric(run_dir, "base", "arabicmmlu")
    ft_mmlu = find_metric(run_dir, "merged", "arabicmmlu") or find_metric(
        run_dir, "eval-model", "arabicmmlu"
    )
    if base_mmlu is not None and ft_mmlu is not None:
        drop = base_mmlu - ft_mmlu
        log.info("arabicmmlu", base=base_mmlu, finetuned=ft_mmlu, drop=round(drop, 2))
        if drop > args.max_arabicmmlu_drop:
            failures.append(
                f"ArabicMMLU drop {drop:.2f} > {args.max_arabicmmlu_drop} pts (forgetting)"
            )
    else:
        failures.append(
            "ArabicMMLU scores missing for base and/or fine-tuned — gate cannot pass blind"
        )

    base_dom = domain_score(run_dir, "base")
    ft_dom = domain_score(run_dir, "finetuned")
    if base_dom is not None and ft_dom is not None:
        delta = ft_dom - base_dom
        log.info("domain_eval", base=base_dom, finetuned=ft_dom, delta=round(delta, 2))
        if delta < args.min_domain_delta:
            failures.append(f"domain delta {delta:.2f} < required +{args.min_domain_delta} pts")
    else:
        failures.append("domain eval scores missing — gate cannot pass blind")

    # judge claims require human validation (prime directive 5)
    judge_report = run_dir / "judge_3c3h.json"
    if judge_report.exists():
        judge = json.loads(judge_report.read_text(encoding="utf-8"))
        if judge.get("human_judge_kappa") is None:
            failures.append(
                "judge scores present but human_judge_kappa missing — no headline judge claims"
            )

    if failures:
        for f in failures:
            log.error("regression_gate_fail", reason=f)
        raise SystemExit(f"regression gate FAILED — {len(failures)} violation(s)")
    log.info("regression_gate_ok", run_id=args.run_id)


if __name__ == "__main__":
    main()
