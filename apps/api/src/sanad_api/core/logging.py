"""structlog JSON logging with a PII-scrub processor (§3.3, §10).

Sovereign logs must never leak prompts with PII: emails, UAE IBAN, Emirates ID and phone
patterns (AR + EN digit forms) are masked in every log value, recursively.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

# Eastern Arabic digits are normalized before matching so ٧٨٤… doesn't slip through.
_EASTERN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email>"),
    (re.compile(r"\bAE\d{21}\b", re.IGNORECASE), "<iban>"),
    (re.compile(r"\b784-?\d{4}-?\d{7}-?\d\b"), "<emirates-id>"),
    (re.compile(r"(?<!\w)(?:\+971|00971|05)\d{8,9}\b"), "<phone>"),  # \b can't precede '+'
]


def scrub(value: str) -> str:
    normalized = value.translate(_EASTERN)
    for pattern, repl in _PII_PATTERNS:
        normalized = pattern.sub(repl, normalized)
    return normalized


def _scrub_any(value: Any) -> Any:
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: _scrub_any(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_scrub_any(v) for v in value)
    return value


def pii_processor(
    logger: structlog.types.WrappedLogger, method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    return {k: _scrub_any(v) for k, v in event_dict.items()}


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            pii_processor,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
