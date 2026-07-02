"""Shared helpers for the data pipeline scripts.

Every pipeline step is idempotent and logs to MLflow (CLAUDE.md §5.1). Normalization for
retrieval/dedup happens on derived *keys* only — the raw text is preserved for SFT.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ML_ROOT / "data" / "schemas" / "record.schema.json"
MANIFEST_PATH = ML_ROOT / "data" / "MANIFEST.yaml"

ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿ]")
LATIN_RE = re.compile(r"[A-Za-z]")

# Arabic-specific normalization for KEYS only (dedup / lang-id), mirroring what CAMeL Tools'
# normalize_* helpers do — kept dependency-light so the base env can run the pipeline.
_AR_DIACRITICS = re.compile(r"[ً-ٰٟـ]")  # harakat + tatweel
_AR_ALEF = re.compile(r"[آأإٱ]")  # آأإٱ → ا
_AR_YA = re.compile(r"[ى]")  # ى → ي
_AR_TA = re.compile(r"[ة]")  # ة → ه


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:  # fail loudly: silent drops skew provenance
                raise ValueError(f"{path}:{i + 1}: invalid JSON — {exc}") from exc


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def nfc(text: str) -> str:
    """Unicode NFC — applied to raw text (safe: canonical composition only)."""
    return unicodedata.normalize("NFC", text)


def dedup_key(text: str) -> str:
    """Aggressive normalization for dedup/lang-id keys — NEVER applied to stored text."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = _AR_DIACRITICS.sub("", t)
    t = _AR_ALEF.sub("ا", t)
    t = _AR_YA.sub("ي", t)
    t = _AR_TA.sub("ه", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def script_ratios(text: str) -> tuple[float, float]:
    """(arabic_ratio, latin_ratio) over script-bearing characters."""
    ar = len(ARABIC_RE.findall(text))
    la = len(LATIN_RE.findall(text))
    total = ar + la
    if total == 0:
        return 0.0, 0.0
    return ar / total, la / total


def record_text(rec: dict[str, Any]) -> str:
    return "\n".join(m["content"] for m in rec.get("messages", []))


def validate_records(records: list[dict[str, Any]]) -> None:
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for rec in records:
        for err in validator.iter_errors(rec):
            errors.append(f"{rec.get('id', '<no-id>')}: {err.message}")
    if errors:
        raise SystemExit("schema validation failed:\n" + "\n".join(errors[:50]))
    log.info("schema_valid", records=len(records))


def mlflow_step(step: str, **params: Any) -> None:
    """Best-effort MLflow logging — the pipeline must run air-gapped without a tracking server."""
    try:
        import mlflow

        with mlflow.start_run(run_name=f"data-{step}", nested=True):
            mlflow.log_params({k: str(v)[:250] for k, v in params.items()})
    except Exception as exc:
        log.debug("mlflow_skip", step=step, reason=str(exc))
