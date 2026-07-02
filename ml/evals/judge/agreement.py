"""Judge disagreement tracking (§5.4c) — the rigor layer on top of run_judges.py.

Outputs (agreement.json, consumed by the dashboard):
  - Krippendorff's α overall + per-dimension (interval metric over 0–5 scores)
  - pairwise judge Cohen's κ (on the binary correctness gate)
  - disagreement heatmap (judge × dimension mean |Δ| from the panel mean)
  - human queue: items with per-item judge spread ≥ 2 → evals/reports/<run>/human_queue.jsonl
  - human↔judge κ once human_scores.jsonl exists (required for any headline judge claim)

Implemented with numpy only — no stats dependency to keep the base env slim.

Usage: uv run python evals/judge/agreement.py --run-id <id>
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[2]
REPORTS = ML_ROOT / "evals" / "reports"
DIMS = ["completeness", "conciseness", "helpfulness", "honesty", "harmlessness"]
HUMAN_QUEUE_SPREAD = 2.0


def krippendorff_alpha(matrix: np.ndarray) -> float:
    """Interval-metric Krippendorff's α. matrix: units × raters, NaN = missing."""
    units = [row[~np.isnan(row)] for row in matrix]
    units = [u for u in units if len(u) >= 2]
    if not units:
        return float("nan")

    # observed disagreement: mean squared pairwise difference within units
    do_num = do_den = 0.0
    for u in units:
        n = len(u)
        diffs = [(a - b) ** 2 for a, b in itertools.combinations(u, 2)]
        do_num += sum(diffs) / (n - 1)
        do_den += n
    do = do_num / do_den if do_den else 0.0

    # expected disagreement: mean squared difference over ALL pairable values
    pooled = np.concatenate(units)
    n_all = len(pooled)
    de = float(np.sum((pooled[:, None] - pooled[None, :]) ** 2)) / (n_all * (n_all - 1))
    if de == 0:
        return 1.0
    return 1.0 - do / de


def cohens_kappa(a: np.ndarray, b: np.ndarray) -> float:
    """Unweighted κ over two binary/categorical vectors of equal length."""
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    if len(a) == 0:
        return float("nan")
    po = float(np.mean(a == b))
    cats = np.union1d(a, b)
    pe = sum(float(np.mean(a == c)) * float(np.mean(b == c)) for c in cats)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def build_matrices(
    rows: list[dict[str, Any]],
) -> tuple[list[str], list[str], dict[str, np.ndarray]]:
    judges = sorted({r["judge"] for r in rows})
    items = sorted({r["item_id"] for r in rows})
    j_ix = {j: i for i, j in enumerate(judges)}
    i_ix = {it: i for i, it in enumerate(items)}

    mats: dict[str, np.ndarray] = {
        key: np.full((len(items), len(judges)), np.nan) for key in ["final", "correct", *DIMS]
    }
    for r in rows:
        row, col = i_ix[r["item_id"]], j_ix[r["judge"]]
        mats["final"][row, col] = r["final"]
        mats["correct"][row, col] = float(r["correct"])
        for d in DIMS:
            mats[d][row, col] = r[d]
    return items, judges, mats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    run_dir = REPORTS / args.run_id
    judge_file = run_dir / "judge_3c3h.json"
    report = json.loads(judge_file.read_text(encoding="utf-8"))
    rows = [r for r in report["rows"] if r["sovereign"]]  # agreement over headline judges only
    if not rows:
        raise SystemExit("no sovereign judge rows — run run_judges.py first")

    items, judges, mats = build_matrices(rows)

    alpha = {"overall": krippendorff_alpha(mats["final"])}
    alpha.update({d: krippendorff_alpha(mats[d]) for d in DIMS})

    pairwise_kappa = {
        f"{a}×{b}": cohens_kappa(mats["correct"][:, ia], mats["correct"][:, ib])
        for (ia, a), (ib, b) in itertools.combinations(enumerate(judges), 2)
    }

    # heatmap: judge × dimension mean absolute deviation from the panel mean
    heatmap = []
    for d in DIMS:
        panel_mean = np.nanmean(mats[d], axis=1)
        for ji, j in enumerate(judges):
            dev = np.nanmean(np.abs(mats[d][:, ji] - panel_mean))
            heatmap.append({"judge": j, "dimension": d, "mean_abs_dev": round(float(dev), 3)})

    # human queue: per-item final-score spread ≥ 2
    spread = np.nanmax(mats["final"], axis=1) - np.nanmin(mats["final"], axis=1)
    queue = [items[i] for i in range(len(items)) if spread[i] >= HUMAN_QUEUE_SPREAD]
    (run_dir / "human_queue.jsonl").write_text(
        "\n".join(json.dumps({"item_id": it}) for it in queue), encoding="utf-8"
    )

    # human validation (protocol: human_validation.md) — κ human↔each judge on correctness
    human_kappa = None
    human_file = run_dir / "human_scores.jsonl"
    if human_file.exists():
        human = {
            json.loads(line)["item_id"]: float(json.loads(line)["correct"])
            for line in human_file.read_text(encoding="utf-8").splitlines()
            if line
        }
        idx = [i for i, it in enumerate(items) if it in human]
        hvec = np.array([human[items[i]] for i in idx])
        kappas = [cohens_kappa(hvec, mats["correct"][idx, ji]) for ji in range(len(judges))]
        human_kappa = float(np.nanmean(kappas))

    agreement = {
        "run_id": args.run_id,
        "judges": judges,
        "items": len(items),
        "krippendorff_alpha": {
            k: None if np.isnan(v) else round(float(v), 4) for k, v in alpha.items()
        },
        "pairwise_cohens_kappa": {
            k: None if np.isnan(v) else round(float(v), 4) for k, v in pairwise_kappa.items()
        },
        "heatmap": heatmap,
        "human_queue": {"threshold_spread": HUMAN_QUEUE_SPREAD, "count": len(queue)},
        "human_judge_kappa": human_kappa,
    }
    (run_dir / "agreement.json").write_text(json.dumps(agreement, indent=2), encoding="utf-8")

    # propagate the human κ into the judge report — regression gate reads it there
    report["human_judge_kappa"] = human_kappa
    judge_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(
        "agreement_done",
        alpha_overall=agreement["krippendorff_alpha"]["overall"],
        human_queue=len(queue),
        human_judge_kappa=human_kappa,
    )
    if human_kappa is None:
        log.warning(
            "no_human_validation",
            note="judge-based claims cannot ship without human κ (prime directive 5)",
        )


if __name__ == "__main__":
    main()
