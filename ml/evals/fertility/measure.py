"""Tokenizer fertility measurement (§5.4d) — the project's signature insight.

tokens/word for {Qwen3, jais-family, ALLaM, Falcon-H1, Llama-3.2} tokenizers over three fixed
corpora (MSA news ~10k words, banking-domain ~5k, English ~10k). Fertility ≈ latency ≈ cost ≈
effective context for Arabic. Output feeds the API (`/v1/tokenize/fertility`) and the 3D hero.

Corpora live at evals/fertility/corpora/{msa_news.txt, banking_ar.txt, english.txt} —
own-collected/CC texts, committed once and frozen (fixed corpora ⇒ comparable numbers).

Usage: uv run python evals/fertility/measure.py --out evals/reports/fertility.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import structlog

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[2]
CORPORA_DIR = Path(__file__).parent / "corpora"

# tokenizer.json is fetched once per model (hub in dev, pre-synced dir in sovereign mode)
TOKENIZERS = {
    "qwen3": "Qwen/Qwen3-4B-Instruct-2507",
    "jais-family": "inceptionai/jais-family-6p7b-chat",
    "allam": "humain-ai/ALLaM-7B-Instruct-preview",
    "falcon-h1": "tiiuae/Falcon-H1-7B-Instruct",
    "llama-3.2": "meta-llama/Llama-3.2-3B-Instruct",
}
CORPORA = {
    "msa_news": CORPORA_DIR / "msa_news.txt",
    "banking_ar": CORPORA_DIR / "banking_ar.txt",
    "english": CORPORA_DIR / "english.txt",
}


def word_count(text: str) -> int:
    return len(text.split())


def load_tokenizer(model_id: str):  # type: ignore[no-untyped-def]
    from tokenizers import Tokenizer

    local = ML_ROOT / "out" / "tokenizers" / model_id.replace("/", "__") / "tokenizer.json"
    if local.exists():
        return Tokenizer.from_file(str(local))
    # dev mode fallback — transformers resolves + caches; sovereign mode must pre-sync
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_id)


def count_tokens(tok, text: str) -> int:  # type: ignore[no-untyped-def]
    if hasattr(tok, "encode") and not hasattr(tok, "apply_chat_template"):
        return len(tok.encode(text).ids)  # tokenizers.Tokenizer
    return len(tok.encode(text))  # transformers tokenizer


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ML_ROOT / "evals" / "reports" / "fertility.json")
    args = ap.parse_args()

    missing = [str(p) for p in CORPORA.values() if not p.exists()]
    if missing:
        raise SystemExit(f"fixed corpora missing (collect once, then freeze): {missing}")

    texts = {name: p.read_text(encoding="utf-8") for name, p in CORPORA.items()}
    words = {name: word_count(t) for name, t in texts.items()}

    results: dict[str, dict[str, dict[str, float]]] = {}
    for tok_name, model_id in TOKENIZERS.items():
        try:
            tok = load_tokenizer(model_id)
        except Exception as exc:
            log.warning("tokenizer_unavailable", tokenizer=tok_name, reason=str(exc))
            continue
        results[tok_name] = {}
        for corpus, text in texts.items():
            n_tokens = count_tokens(tok, text)
            fertility = n_tokens / words[corpus]
            results[tok_name][corpus] = {
                "tokens": n_tokens,
                "words": words[corpus],
                "tokens_per_word": round(fertility, 4),
            }
            log.info("fertility", tokenizer=tok_name, corpus=corpus, tpw=round(fertility, 3))

    # relative cost vs the best (lowest-fertility) tokenizer per corpus — the HUD's Δcost
    for corpus in CORPORA:
        best = min(
            (r[corpus]["tokens_per_word"] for r in results.values() if corpus in r),
            default=None,
        )
        if best:
            for r in results.values():
                if corpus in r:
                    r[corpus]["cost_vs_best"] = round(r[corpus]["tokens_per_word"] / best, 4)

    payload = {
        "tokenizers": {k: TOKENIZERS[k] for k in results},
        "corpora": list(CORPORA),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("fertility_written", out=str(args.out), tokenizers=len(results))


if __name__ == "__main__":
    main()
