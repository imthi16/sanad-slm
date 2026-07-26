"""Draft synthetic banking/compliance pairs from grounded seeds via a LOCAL ollama model.

Every pair produced here is `provenance: synthetic` with no reviewer — see the honesty
contract at the top of data/seeds/bank_topics.yaml. This closes the P1 pipeline so the rest
of the stack can be exercised end-to-end; it does not substitute for the own-authored native
pairs §5.1 calls for, and the MANIFEST keeps the two visibly apart.

Why ollama rather than an API judge/generator: it is already resident on the train box, costs
nothing, and keeps generation inside the sovereign boundary (prime directive 1). Generation
is seeded per (topic, angle, lang) so a rerun reproduces the same drafts (prime directive 4).

Usage:
    python data/scripts/gen_bank_synthetic.py                    # dry run: show the work plan
    python data/scripts/gen_bank_synthetic.py --emit             # generate + write YAML
    python data/scripts/gen_bank_synthetic.py --emit --limit 5   # smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import structlog
import yaml
from _lib import ML_ROOT

sys.path.insert(0, str(Path(__file__).parent))
from curate_bank import pii_scan  # sibling script, not a package

log = structlog.get_logger()

SEEDS = ML_ROOT / "data" / "seeds" / "bank_topics.yaml"
OUT_DIR = ML_ROOT / "data" / "raw" / "bank"

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:32b"
PAIRS_PER_CALL = 4

# 60 / 30 / 10 per §5.1. Applied over the (topic × angle) grid, so each language still sees
# every topic and every angle rather than a contiguous block of the corpus.
LANG_CYCLE = ["ar"] * 6 + ["en"] * 3 + ["mixed"]

LANG_RULES = {
    "ar": (
        "Write BOTH the question and the answer in Modern Standard Arabic (فصحى). "
        "No dialect, no English words except unavoidable proper nouns."
    ),
    "en": "Write BOTH the question and the answer in English.",
    "mixed": (
        "Write realistic Gulf banking code-switching: an Arabic sentence frame that keeps "
        "common English banking terms inline (e.g. KYC, compliance, statement, LTV). "
        "Both question and answer must mix the two scripts naturally."
    ),
}

ANGLE_RULES = {
    "definition": "Ask what something is and have the answer define it precisely.",
    "threshold": "Ask about a limit, timeframe or condition stated in the grounding.",
    "procedure": "Ask what steps the bank or customer must take, in order.",
    "exception": "Ask when the rule does NOT apply, or what is carved out.",
    "customer_facing": (
        "Ask as an ordinary retail customer would, in plain non-expert words; "
        "the answer must avoid jargon and explain it simply."
    ),
    "escalation": "Ask what to do when something is wrong, suspicious or disputed.",
    "recordkeeping": "Ask what must be recorded or retained, and for how long.",
}

PROMPT = """You are drafting supervised fine-tuning data for a UAE banking and compliance assistant.

GROUNDING (the only facts you may assert):
{grounding}

GOVERNING INSTRUMENT (for context only — do NOT quote article numbers): {citation}

TASK: write {n} DIFFERENT question-and-answer pairs about this grounding.
ANGLE: {angle_rule}
LANGUAGE: {lang_rule}

HARD RULES:
- Assert nothing that is not supported by the grounding above. Do not invent article numbers,
  specific figures, percentages, dates or fee amounts that are not in the grounding.
- No personal data of any kind: no names, emails, phone numbers, IBANs, Emirates ID numbers.
- Each answer is 2-5 sentences, direct and professional. No preamble, no bullet lists.
- The {n} pairs must differ from each other in wording and in what they ask.

Return ONLY JSON: {{"pairs": [{{"question": "...", "answer": "..."}}]}}"""


def build_plan(seeds: dict[str, Any]) -> list[dict[str, str]]:
    """(topic × angle) grid with languages dealt round-robin to hit the 60/30/10 target."""
    angles: list[str] = seeds["angles"]
    plan: list[dict[str, str]] = []
    i = 0
    for topic in seeds["topics"]:
        for angle in angles:
            plan.append(
                {
                    "topic_id": topic["id"],
                    "domain": topic["domain"],
                    "citation": topic["citation"],
                    "grounding": " ".join(topic["grounding"].split()),
                    "angle": angle,
                    "lang": LANG_CYCLE[i % len(LANG_CYCLE)],
                }
            )
            i += 1
    return plan


def generate(client: httpx.Client, job: dict[str, str], seed: int) -> list[dict[str, str]]:
    prompt = PROMPT.format(
        grounding=job["grounding"],
        citation=job["citation"],
        n=PAIRS_PER_CALL,
        angle_rule=ANGLE_RULES[job["angle"]],
        lang_rule=LANG_RULES[job["lang"]],
    )
    resp = client.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.85, "top_p": 0.95, "seed": seed, "num_predict": 1400},
        },
        timeout=600.0,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    parsed = json.loads(content)
    pairs = parsed.get("pairs", parsed) if isinstance(parsed, dict) else parsed
    if not isinstance(pairs, list):
        return []

    out: list[dict[str, str]] = []
    for p in pairs:
        if not isinstance(p, dict):
            continue
        q, a = str(p.get("question", "")).strip(), str(p.get("answer", "")).strip()
        # Drop rather than repair: a PII hit or a stub is cheaper to regenerate than to audit.
        if len(q) < 10 or len(a) < 20 or pii_scan(q) or pii_scan(a):
            continue
        out.append({"question": q, "answer": a})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit", action="store_true", help="write YAML drafts (else dry-run)")
    ap.add_argument("--limit", type=int, default=None, help="cap jobs (smoke test)")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    seeds = yaml.safe_load(SEEDS.read_text(encoding="utf-8"))
    plan = build_plan(seeds)
    if args.limit:
        plan = plan[: args.limit]

    langs = [j["lang"] for j in plan]
    log.info(
        "plan",
        jobs=len(plan),
        expected_pairs=len(plan) * PAIRS_PER_CALL,
        lang_split={ln: round(langs.count(ln) / len(langs), 3) for ln in ("ar", "en", "mixed")},
    )
    if not args.emit:
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_topic: dict[str, list[dict[str, str]]] = {}
    failures = 0

    with httpx.Client() as client:
        for n, job in enumerate(plan):
            try:
                pairs = generate(client, job, seed=3407 + n)
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
                failures += 1
                log.warning("job_failed", topic=job["topic_id"], angle=job["angle"], err=str(exc))
                continue

            by_topic.setdefault(job["topic_id"], []).extend(
                {
                    "question": p["question"],
                    "answer": p["answer"],
                    "citation": job["citation"],
                    "domain": job["domain"],
                    "lang": job["lang"],
                    "provenance": "synthetic",
                }
                for p in pairs
            )
            if (n + 1) % 10 == 0:
                total = sum(len(v) for v in by_topic.values())
                log.info("progress", done=n + 1, of=len(plan), pairs=total, failed=failures)

    for topic_id, drafts in by_topic.items():
        (OUT_DIR / f"synthetic_{topic_id}.yaml").write_text(
            yaml.safe_dump(drafts, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )

    total = sum(len(v) for v in by_topic.values())
    log.info("emitted", topics=len(by_topic), pairs=total, failed_jobs=failures, out=str(OUT_DIR))


if __name__ == "__main__":
    main()
