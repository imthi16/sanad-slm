"""Language tagging pass (idempotent, in-place over processed shards).

Primary signal: character-script ratios — tag `mixed` when BOTH scripts exceed 15% (§5.1).
Secondary signal (when the `arabic` extra is installed): fasttext lid.176 sanity check;
disagreements are logged, script-ratio wins (fasttext is unreliable on short code-switch text).

Usage: python data/scripts/langid.py <dir>
"""

from __future__ import annotations

import argparse
from pathlib import Path

import structlog
from _lib import mlflow_step, read_jsonl, record_text, script_ratios, write_jsonl

log = structlog.get_logger()

MIXED_THRESHOLD = 0.15


def detect_lang(text: str) -> str:
    ar, la = script_ratios(text)
    if ar > MIXED_THRESHOLD and la > MIXED_THRESHOLD:
        return "mixed"
    return "ar" if ar >= la else "en"


def _fasttext_check(texts: list[str], tags: list[str]) -> None:
    try:
        import fasttext

        model_path = Path(__file__).parents[2] / "out" / "lid.176.bin"
        if not model_path.exists():
            log.debug("fasttext_skip", reason="lid.176.bin not present (offline ok)")
            return
        model = fasttext.load_model(str(model_path))
        disagreements = 0
        for text, tag in zip(texts, tags, strict=True):
            labels, _ = model.predict(text.replace("\n", " ")[:1000])
            ft = labels[0].removeprefix("__label__")
            if tag != "mixed" and ft in ("ar", "en") and ft != tag:
                disagreements += 1
        log.info("fasttext_crosscheck", disagreements=disagreements, total=len(texts))
    except ImportError:
        log.debug("fasttext_skip", reason="arabic extra not installed")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir", type=Path)
    args = ap.parse_args()

    total = 0
    for shard in sorted(args.dir.glob("*.jsonl")):
        records = list(read_jsonl(shard))
        texts = [record_text(r) for r in records]
        tags = [detect_lang(t) for t in texts]
        for rec, tag in zip(records, tags, strict=True):
            rec["lang"] = tag
        _fasttext_check(texts, tags)
        write_jsonl(shard, records)
        total += len(records)
        counts = {t: tags.count(t) for t in ("ar", "en", "mixed")}
        log.info("langid", file=shard.name, **counts)

    mlflow_step("langid", dir=str(args.dir), records=total)


if __name__ == "__main__":
    main()
