"""Measure the Specimen sentence through the real fertility service (demo asset generator).

The README's hero recording used to be driven by hand-written fixture data — not just the token
*counts* but the token *boundaries*, which are the thing the Specimen exists to show. Fabricated
boundaries are a typographic claim about a tokenizer that the tokenizer never made, and one of the
fixture rows even inverted the project's own finding (English split, Arabic left whole). So the
recording is now driven by this: the same `measure_sync` the `/v1/tokenize/fertility` endpoint
calls, over the tokenizer.json files `just sync-tokenizers` puts in `ml/out/tokenizers/`.

Two of the five tokenizers in §5.4d sit behind manual access gates and are absent here. They are
reported in `absent` and the web ledger renders them as `—`, which is the correct product
behaviour for an unmeasured row (§8.2) and is more honest than inventing plausible numbers.

This is **not** the corpus-level fertility benchmark: it prices one sentence, not the three frozen
corpora `just fertility` needs. Nothing it emits may be quoted as a fertility result.

Usage:
    uv run python scripts/measure_specimen.py                       # → docs/screenshots/…json
    uv run python scripts/measure_specimen.py --text "…" --out /tmp/p.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sanad_api.services.fertility import KNOWN_TOKENIZERS, measure_sync

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TOKENIZERS = REPO_ROOT / "ml" / "out" / "tokenizers"
DEFAULT_OUT = REPO_ROOT / "docs" / "screenshots" / "specimen-demo-payload.json"

#: The web app's default specimen (apps/web/src/store/tokenizer.ts) — kept in step deliberately,
#: so the committed payload is the one the hero requests on first paint.
SPECIMEN = "يخضع حساب التوفير لمعدل فائدة سنوي قدره 2.75% subject to CBUAE regulations"


def revisions(tokenizers_dir: Path) -> dict[str, Any]:
    """The resolved revision per tokenizer, as recorded by `just sync-tokenizers`.

    A tokens/word figure means nothing without the tokenizer version behind it — vocabularies do
    change between releases.
    """
    manifest = tokenizers_dir / "tokenizers.manifest.json"
    if not manifest.exists():
        return {}
    loaded: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    return loaded


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tokenizers-dir", type=Path, default=DEFAULT_TOKENIZERS)
    ap.add_argument("--text", default=SPECIMEN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    tokenizers_dir: Path = args.tokenizers_dir.expanduser()
    result = measure_sync(str(tokenizers_dir), args.text)
    measured = sorted(result["tokenizers"])
    if not measured:
        raise SystemExit(
            f"no tokenizer.json found under {tokenizers_dir} — run `just sync-tokenizers` first "
            "(needs network access and an HF_TOKEN for the gated repos)"
        )

    manifest = revisions(tokenizers_dir)
    result["x_provenance"] = {
        "kind": "measured",
        "produced_by": "apps/api/scripts/measure_specimen.py via services.fertility.measure_sync",
        "note": (
            "Real tokenizer output for one sentence — the same call /v1/tokenize/fertility serves. "
            "NOT the corpus-level fertility benchmark (§5.4d), which needs the three frozen "
            "corpora and is not runnable yet. Do not quote as a fertility result."
        ),
        "text": args.text,
        "tokenizers": {name: manifest.get(name, {"revision": "unrecorded"}) for name in measured},
        "absent": {
            name: "not synced — gated repository, manual access approval outstanding"
            for name in KNOWN_TOKENIZERS
            if name not in result["tokenizers"]
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic: the same tokenizers and sentence must produce the same bytes, so re-recording
    # the demo does not churn the diff.
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "measured": measured,
                "absent": sorted(result["x_provenance"]["absent"]),
                "tokens_per_word": {
                    k: v["tokens_per_word"] for k, v in sorted(result["tokenizers"].items())
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
