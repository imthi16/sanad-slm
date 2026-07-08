"""Curation tool for own-authored banking/compliance SFT pairs (CC-BY-4.0, ours).

Template per §5.1: question, grounded answer, source citation field, reviewer initials.
Target 800–1,500 pairs at 60% AR / 30% EN / 10% code-switch. Drafts are authored as YAML
files under data/raw/bank/*.yaml; this script validates them, enforces the template, runs
the PII check, and emits schema-valid records.

Draft YAML shape (one file may hold many):
    - question: "ما هي متطلبات اعرف عميلك للحسابات الجديدة؟"
      answer: "..."
      citation: "CBUAE Rulebook, AML/CFT Decision No. (20) of 2018, Art. 8"
      domain: banking.compliance
      lang: ar            # optional; re-checked by langid pass
      reviewer: "MO"      # initials — required

Usage: python data/scripts/curate_bank.py [--emit]
"""

from __future__ import annotations

import argparse
import re
from typing import Any

import structlog
import yaml
from _lib import ML_ROOT, mlflow_step, write_jsonl

log = structlog.get_logger()

RAW_BANK = ML_ROOT / "data" / "raw" / "bank"
OUT = ML_ROOT / "data" / "raw" / "bank_records.jsonl"
SOURCE = {"name": "sanad-bank-pairs", "url": "local:data/raw/bank", "license": "CC-BY-4.0"}

# PII patterns — AR + EN: emails, UAE IBAN, Emirates ID, phone numbers (§10 posture).
PII_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"\bAE\d{21}\b", re.IGNORECASE),  # UAE IBAN
    re.compile(r"\b784-?\d{4}-?\d{7}-?\d\b"),  # Emirates ID
    re.compile(r"(?<!\w)(?:\+971|00971|05)\d{8,9}\b"),  # UAE phone (\b can't precede '+')
]

VALID_DOMAINS = {"banking.compliance", "banking.retail", "banking.corporate", "banking.islamic"}


def pii_scan(text: str) -> list[str]:
    return [p.pattern for p in PII_PATTERNS if p.search(text)]


def validate_draft(d: dict[str, Any], where: str) -> list[str]:
    errors = []
    for field in ("question", "answer", "citation", "domain", "reviewer"):
        if not d.get(field):
            errors.append(f"{where}: missing required field '{field}' (template §5.1)")
    if d.get("domain") and d["domain"] not in VALID_DOMAINS:
        errors.append(f"{where}: domain '{d['domain']}' ∉ {sorted(VALID_DOMAINS)}")
    for field in ("question", "answer"):
        if hits := pii_scan(str(d.get(field, ""))):
            errors.append(f"{where}: PII pattern hit in {field}: {hits}")
    return errors


def to_record(d: dict[str, Any], idx: int) -> dict[str, Any]:
    lang = d.get("lang", "ar")
    return {
        "id": f"bank-{lang}-{idx:06d}",
        "messages": [
            {"role": "user", "content": str(d["question"]).strip()},
            {"role": "assistant", "content": str(d["answer"]).strip()},
        ],
        "lang": lang,
        "domain": [d["domain"]],
        "provenance": "native",
        "source": {**SOURCE, "citation": d["citation"], "reviewer": d["reviewer"]},
        "pii_checked": True,  # asserted only after pii_scan passed
        "split": "train",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit", action="store_true", help="write bank_records.jsonl (else dry-run)")
    args = ap.parse_args()

    drafts: list[tuple[dict[str, Any], str]] = []
    for f in sorted(RAW_BANK.glob("*.yaml")) if RAW_BANK.exists() else []:
        loaded = yaml.safe_load(f.read_text(encoding="utf-8")) or []
        drafts.extend((d, f"{f.name}[{i}]") for i, d in enumerate(loaded))

    errors = [e for d, where in drafts for e in validate_draft(d, where)]
    if errors:
        raise SystemExit("curation validation failed:\n" + "\n".join(errors))

    langs = [d.get("lang", "ar") for d, _ in drafts]
    split = {ln: langs.count(ln) / len(langs) for ln in ("ar", "en", "mixed")} if langs else {}
    log.info("curation_ok", drafts=len(drafts), lang_split=split, target="60/30/10 ar/en/mixed")

    if args.emit and drafts:
        records = [to_record(d, i) for i, (d, _) in enumerate(drafts)]
        n = write_jsonl(OUT, records)
        log.info("emitted", records=n, out=str(OUT))
        mlflow_step("curate_bank", records=n)


if __name__ == "__main__":
    main()
