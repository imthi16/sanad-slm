"""Live tokenizer fertility service — powers POST /v1/tokenize/fertility and the 3D hero.

Tokenizers load lazily from pre-synced tokenizer.json files (sovereign: no hub fetch, ever).
For each tokenizer: token count, tokens/word, and the token segments (offsets + script tag)
that FertilityField uses to animate glyph clusters.
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from sanad_api.services.inference_router import detect_lang

log = structlog.get_logger()

# alias → tokenizer.json dir name under settings.tokenizers_dir (pre-synced by initContainer)
KNOWN_TOKENIZERS = {
    "qwen3": "Qwen__Qwen3-4B-Instruct-2507",
    "jais-family": "inceptionai__jais-family-6p7b-chat",
    "allam": "humain-ai__ALLaM-7B-Instruct-preview",
    "falcon-h1": "tiiuae__Falcon-H1-7B-Instruct",
    "llama-3.2": "meta-llama__Llama-3.2-3B-Instruct",
}


@lru_cache(maxsize=8)
def _load(tokenizers_dir: str, name: str) -> Any | None:
    from tokenizers import Tokenizer

    path = Path(tokenizers_dir) / KNOWN_TOKENIZERS[name] / "tokenizer.json"
    if not path.exists():
        log.warning("tokenizer_missing", tokenizer=name, path=str(path))
        return None
    return Tokenizer.from_file(str(path))


def _segments(tokenizer: Any, text: str) -> list[dict[str, Any]]:
    enc = tokenizer.encode(text)
    segments = []
    for token_id, (start, end) in zip(enc.ids, enc.offsets, strict=True):
        piece = text[start:end]
        if not piece:
            continue  # specials / zero-width offsets
        segments.append(
            {
                "id": token_id,
                "start": start,
                "end": end,
                "text": piece,
                "script": detect_lang(piece),
            }
        )
    return segments


def measure_sync(tokenizers_dir: str, text: str) -> dict[str, Any]:
    words = max(len(text.split()), 1)
    result: dict[str, Any] = {
        "text_words": words,
        "detected_lang": detect_lang(text),
        "tokenizers": {},
    }
    for name in KNOWN_TOKENIZERS:
        tok = _load(tokenizers_dir, name)
        if tok is None:
            continue
        segments = _segments(tok, text)
        result["tokenizers"][name] = {
            "tokens": len(segments),
            "tokens_per_word": round(len(segments) / words, 4),
            "segments": segments,
        }
    best = min(
        (v["tokens_per_word"] for v in result["tokenizers"].values()),
        default=None,
    )
    if best:
        for v in result["tokenizers"].values():
            v["cost_vs_best"] = round(v["tokens_per_word"] / best, 4)
    return result


async def measure(tokenizers_dir: str, text: str) -> dict[str, Any]:
    # tokenization is CPU-bound Rust — keep the event loop free
    return await asyncio.to_thread(measure_sync, tokenizers_dir, text)


def load_static_report(path: str) -> dict[str, Any] | None:
    """The frozen fertility.json from ml/evals (corpus-level numbers for the Evals page)."""
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
