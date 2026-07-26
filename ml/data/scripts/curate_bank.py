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
      provenance: native  # optional, default native; native | synthetic | translated
      reviewer: "MO"      # initials — required for provenance: native

`reviewer` is an attestation that a human checked the pair, so it is required exactly when
the draft claims `provenance: native`. A machine-drafted pair enters as `synthetic` with no
reviewer and earns both fields when a human promotes it — that ordering is what keeps the
MANIFEST's native/translated/synthetic split truthful (prime directive 3).

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
VALID_PROVENANCE = {"native", "synthetic", "translated"}


def pii_scan(text: str) -> list[str]:
    return [p.pattern for p in PII_PATTERNS if p.search(text)]


def validate_draft(d: dict[str, Any], where: str) -> list[str]:
    errors = []
    provenance = d.get("provenance", "native")
    if provenance not in VALID_PROVENANCE:
        errors.append(f"{where}: provenance '{provenance}' ∉ {sorted(VALID_PROVENANCE)}")

    required = ["question", "answer", "citation", "domain"]
    if provenance == "native":
        required.append("reviewer")  # the human attestation — see module docstring
    for field in required:
        if not d.get(field):
            errors.append(f"{where}: missing required field '{field}' (template §5.1)")

    if provenance != "native" and d.get("reviewer"):
        errors.append(
            f"{where}: provenance '{provenance}' carries a reviewer — a reviewed pair is "
            "native; promote it by setting provenance: native instead"
        )
    if d.get("domain") and d["domain"] not in VALID_DOMAINS:
        errors.append(f"{where}: domain '{d['domain']}' ∉ {sorted(VALID_DOMAINS)}")
    for field in ("question", "answer"):
        if hits := pii_scan(str(d.get(field, ""))):
            errors.append(f"{where}: PII pattern hit in {field}: {hits}")
    return errors


def to_record(d: dict[str, Any], idx: int) -> dict[str, Any]:
    lang = d.get("lang", "ar")
    provenance = d.get("provenance", "native")
    # Non-native origin is carried in the id as well as the provenance field, so a
    # mislabelled record is visible in any plain listing, not only after a schema read.
    marker = "" if provenance == "native" else "-syn"
    source = {**SOURCE, "citation": d["citation"]}
    if reviewer := d.get("reviewer"):
        source["reviewer"] = reviewer
    return {
        "id": f"bank{marker}-{lang}-{idx:06d}",
        "messages": [
            {"role": "user", "content": str(d["question"]).strip()},
            {"role": "assistant", "content": str(d["answer"]).strip()},
        ],
        "lang": lang,
        "domain": [d["domain"]],
        "provenance": provenance,
        "source": source,
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
    provs = [d.get("provenance", "native") for d, _ in drafts]
    split = {ln: langs.count(ln) / len(langs) for ln in ("ar", "en", "mixed")} if langs else {}
    prov_split = {p: provs.count(p) for p in sorted(VALID_PROVENANCE)} if provs else {}
    log.info(
        "curation_ok",
        drafts=len(drafts),
        lang_split=split,
        provenance=prov_split,
        target="60/30/10 ar/en/mixed",
    )
    if unreviewed := provs.count("synthetic"):
        log.warning(
            "synthetic_pending_review",
            count=unreviewed,
            note="machine-drafted; not native until a human reviews and promotes each pair",
        )

    if args.emit and drafts:
        records = [to_record(d, i) for i, (d, _) in enumerate(drafts)]
        n = write_jsonl(OUT, records)
        log.info("emitted", records=n, out=str(OUT))
        mlflow_step("curate_bank", records=n)


if __name__ == "__main__":
    main()
