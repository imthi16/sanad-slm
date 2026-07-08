"""3C3H multi-judge harness (§5.4c).

Pipeline per run:
  1. --answers-only: generate the tested model's answers for sanad_bank_eval_v1 (+ exact-match /
     classification scoring, which needs no judge) → domain_<model>.json
  2. default: score grounded_qa answers with every configured judge (rubric in the item's
     language; correctness binary gate, then five 1–5 dimensions) → judge_3c3h.json
  3. --ingest: POST the reports to the API (`/v1/eval/runs/{id}/ingest`, bearer service token).

Judge pool rule (hard): never a judge from the tested model's family. Non-sovereign
(dev calibration) judges are stored with sovereign=false and excluded from headline scores.

Usage:
    uv run python evals/judge/run_judges.py --run-id 20260702a [--answers-only] [--ingest]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
import structlog
import yaml

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ML_ROOT / "data" / "scripts"))

CFG = yaml.safe_load((ML_ROOT / "configs" / "eval" / "judge_3c3h.yaml").read_text(encoding="utf-8"))
DOMAIN_SET = ML_ROOT / "evals" / "domain" / "sanad_bank_eval_v1.jsonl"
REPORTS = ML_ROOT / "evals" / "reports"

DIMS = CFG["scoring"]["dimensions"]
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def expand_env(value: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def active_judges(mode: str, tested_family: str) -> list[dict[str, Any]]:
    judges = []
    for j in CFG["judges"]:
        if j.get("dev_only") and mode != "dev":
            continue
        if tested_family.lower() in j["model"].lower():
            raise SystemExit(
                f"judge '{j['name']}' is from the tested model's family '{tested_family}' — "
                "self-preference bias; fix configs/eval/judge_3c3h.yaml"
            )
        j = {**j, "base_url": expand_env(str(j["base_url"])), "model": expand_env(str(j["model"]))}
        if j["base_url"]:
            judges.append(j)
    if not judges:
        raise SystemExit("no judges resolvable — are the judge vLLM pods up?")
    return judges


def chat(
    client: httpx.Client,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 768,
) -> str:
    r = client.post(
        f"{base_url}/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "temperature": CFG["scoring"]["temperature"],
            "max_tokens": max_tokens,
        },
        timeout=120,
    )
    r.raise_for_status()
    return str(r.json()["choices"][0]["message"]["content"])


def load_items() -> list[dict[str, Any]]:
    from _lib import read_jsonl

    return list(read_jsonl(DOMAIN_SET))


def norm_answer(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().strip(".。").lower()


def generate_answers(run_id: str, model_url: str, model_name: str) -> None:
    """Answer all 300 items with the model under test; score the judge-free tasks."""
    items = load_items()
    out_dir = REPORTS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    answers, em_hits, cls_hits, em_n, cls_n = [], 0, 0, 0, 0
    with httpx.Client() as client:
        for item in items:
            prompt = [m for m in item["messages"] if m["role"] == "user"]
            reply = chat(client, model_url, model_name, prompt, max_tokens=512)
            answers.append(
                {
                    "id": item["id"],
                    "answer": reply,
                    "lang": item["lang"],
                    "task": item["eval"]["task"],
                }
            )
            if item["eval"]["task"] == "extraction":
                em_n += 1
                em_hits += int(norm_answer(reply) == norm_answer(item["eval"]["answer"]))
            elif item["eval"]["task"] == "classification":
                cls_n += 1
                gold = norm_answer(item["eval"]["answer"])
                cls_hits += int(gold in norm_answer(reply))

    (out_dir / "answers_finetuned.jsonl").write_text(
        "\n".join(json.dumps(a, ensure_ascii=False) for a in answers), encoding="utf-8"
    )
    scores = {
        "extraction_exact_match": em_hits / em_n * 100 if em_n else None,
        "classification_accuracy": cls_hits / cls_n * 100 if cls_n else None,
    }
    numeric = [v for v in scores.values() if v is not None]
    report = {
        "run_id": run_id,
        "model": model_name,
        "scores": scores,
        "aggregate_score": sum(numeric) / len(numeric) if numeric else 0.0,
    }
    (out_dir / "domain_finetuned.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("answers_done", **{k: v for k, v in scores.items() if v is not None})


def parse_judgment(raw: str) -> dict[str, Any] | None:
    m = JSON_RE.search(raw)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if "correct" not in j:
        return None
    if not bool(j["correct"]):
        return {"correct": False, "final": 0.0, **{d: 0 for d in DIMS}}
    if any(d not in j or not 1 <= int(j[d]) <= 5 for d in DIMS):
        return None
    dims = {d: int(j[d]) for d in DIMS}
    return {"correct": True, "final": sum(dims.values()) / len(dims), **dims}


def judge_answers(run_id: str) -> None:
    mode = os.environ.get("SANAD_MODE", "dev")
    tested_family = os.environ.get("SANAD_TESTED_FAMILY", "qwen")
    judges = active_judges(mode, tested_family)
    items = {i["id"]: i for i in load_items()}
    out_dir = REPORTS / run_id
    answers = [
        json.loads(line)
        for line in (out_dir / "answers_finetuned.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    qa_answers = [a for a in answers if a["task"] == "grounded_qa"]

    rubrics = {
        "ar": (ML_ROOT / CFG["rubrics"]["ar"]).read_text(encoding="utf-8"),
        "en": (ML_ROOT / CFG["rubrics"]["en"]).read_text(encoding="utf-8"),
    }

    rows: list[dict[str, Any]] = []
    with httpx.Client() as client:
        for a in qa_answers:
            item = items[a["id"]]
            rubric = rubrics["ar" if item["lang"] in ("ar", "mixed") else "en"]
            question = next(m["content"] for m in item["messages"] if m["role"] == "user")
            gold = next(m["content"] for m in item["messages"] if m["role"] == "assistant")
            prompt = (
                f"{rubric}\n\n---\n### Question\n{question}\n\n"
                f"### Gold reference\n{gold}\n\n"
                f"### Grounding\n{item['eval'].get('grounding', '—')}\n\n"
                f"### Answer under evaluation\n{a['answer']}\n"
            )
            for j in judges:
                raw = chat(client, j["base_url"], j["model"], [{"role": "user", "content": prompt}])
                parsed = parse_judgment(raw)
                if parsed is None:
                    log.warning("judgment_unparseable", judge=j["name"], item=a["id"])
                    continue
                rows.append(
                    {
                        "item_id": a["id"],
                        "lang": item["lang"],
                        "judge": j["name"],
                        "sovereign": bool(j["sovereign"]),
                        **parsed,
                    }
                )

    sov = [r for r in rows if r["sovereign"]]
    per_dim = {d: (sum(r[d] for r in sov) / len(sov) if sov else 0.0) for d in DIMS}
    headline_final = sum(r["final"] for r in sov) / len(sov) if sov else 0.0
    report: dict[str, Any] = {
        "run_id": run_id,
        "judges": [j["name"] for j in judges],
        "items_judged": len(qa_answers),
        "headline_final": headline_final,
        "per_dimension": per_dim,
        "correct_rate": sum(r["correct"] for r in sov) / len(sov) if sov else 0.0,
        "non_sovereign_excluded": len(rows) - len(sov),
        "human_judge_kappa": None,  # set by agreement.py once human_scores.jsonl exists
        "rows": rows,
    }
    (out_dir / "judge_3c3h.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(
        "judging_done",
        items=len(qa_answers),
        judges=len(judges),
        headline=round(headline_final, 3),
    )


def ingest(run_id: str, api_url: str) -> None:
    token = os.environ.get("SANAD_SERVICE_TOKEN", "")
    out_dir = REPORTS / run_id
    payload: dict[str, Any] = {"run_id": run_id, "reports": {}}
    for name in ("domain_finetuned.json", "judge_3c3h.json", "agreement.json", "fertility.json"):
        f = out_dir / name if name != "fertility.json" else REPORTS / name
        if f.exists():
            payload["reports"][name.removesuffix(".json")] = json.loads(
                f.read_text(encoding="utf-8")
            )
    r = httpx.post(
        f"{api_url}/v1/eval/runs/{run_id}/ingest",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    r.raise_for_status()
    log.info("ingested", run_id=run_id, api=api_url, reports=list(payload["reports"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--answers-only", action="store_true")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--api-url", default=os.environ.get("SANAD_API_URL", "http://localhost:8000"))
    ap.add_argument(
        "--model-url", default=os.environ.get("SANAD_MODEL_URL", "http://localhost:8000/v1")
    )
    ap.add_argument("--model-name", default=os.environ.get("SANAD_MODEL_NAME", "sanad-bank-awq"))
    args = ap.parse_args()

    if args.ingest:
        ingest(args.run_id, args.api_url)
    elif args.answers_only:
        generate_answers(args.run_id, args.model_url, args.model_name)
    else:
        if not (REPORTS / args.run_id / "answers_finetuned.jsonl").exists():
            generate_answers(args.run_id, args.model_url, args.model_name)
        judge_answers(args.run_id)


if __name__ == "__main__":
    main()
