"""Sync the five `tokenizer.json` files the fertility measurement needs (§5.4d).

`measure.py` looks for `out/tokenizers/<org>__<model>/tokenizer.json` and the API's fertility
service looks for the same layout under `settings.tokenizers_dir`. Nothing fetched them, which is
why `/v1/tokenize/fertility` returned an empty tokenizer map — the Specimen hero had no real
numbers to show — and why sovereign mode could never have worked at all: it forbids hub access, so
the files must already be on disk.

**Tokenizers only, never weights.** Each file is a few MB against gigabytes for a checkpoint, and
fertility is a property of the vocabulary alone. Nothing here downloads a model.

**Records the revision it resolved.** A tokenizer that changes underneath a published
tokens/word figure invalidates it silently, so the resolved sha for each is written to
`tokenizers.manifest.json` beside the files (prime directive 4).

**Gated models are reported, not fatal.** `meta-llama/Llama-3.2-3B-Instruct` needs manual approval
from Meta and `inceptionai/jais-family-6p7b-chat` needs accepted terms plus a token (§15). Failing
the whole sync because one of five is pending would block the other four, so each is reported with
what it needs and the exit code reflects only whether anything usable landed.

Usage: uv run python evals/fertility/sync_tokenizers.py [--out DIR] [--only qwen3,allam]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import structlog
from huggingface_hub import HfApi

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ML_ROOT / "out" / "tokenizers"

#: alias → hub id. Kept in step with measure.py's TOKENIZERS and the API's KNOWN_TOKENIZERS;
#: test_fertility_sync.py asserts all three agree so a rename cannot desync them.
TOKENIZERS = {
    "qwen3": "Qwen/Qwen3-4B-Instruct-2507",
    "jais-family": "inceptionai/jais-family-6p7b-chat",
    "allam": "humain-ai/ALLaM-7B-Instruct-preview",
    "falcon-h1": "tiiuae/Falcon-H1-7B-Instruct",
    "llama-3.2": "meta-llama/Llama-3.2-3B-Instruct",
}

#: what to tell the user when the hub refuses, keyed by the gating we already documented in §15
GATED_HINT = {
    "meta-llama/Llama-3.2-3B-Instruct": (
        "gated: manual — Meta approves each request by hand. Request access on the model page, "
        "then set HF_TOKEN."
    ),
    "inceptionai/jais-family-6p7b-chat": (
        "gated: auto — accept the terms once on the model page while signed in, then set HF_TOKEN."
    ),
}


def target_dir(out_root: Path, model_id: str) -> Path:
    """`org/model` → `org__model`, the layout measure.py and the API both expect."""
    return out_root / model_id.replace("/", "__")


def snapshot_revision(cached: str) -> str:
    """The hub caches as .../snapshots/<sha>/<file>, so the parent directory *is* the revision."""
    parent = Path(cached).parent
    return parent.name if parent.parent.name == "snapshots" else "unknown"


def convert_from_sentencepiece(model_id: str, dest: Path) -> tuple[bool, str]:
    """Build tokenizer.json for repos that ship only sentencepiece (ALLaM is one).

    Both consumers read tokenizer.json and nothing else — the API's loader has no sentencepiece
    path at all — so a repo without one is simply absent from the fertility table unless it is
    converted here. transformers can produce the fast tokenizer; it lives in the `train` extra.
    """
    try:
        from transformers import AutoTokenizer
    except ImportError:
        return False, (
            "no tokenizer.json upstream; converting from sentencepiece needs transformers "
            "(uv sync --extra train)"
        )
    try:
        tok = AutoTokenizer.from_pretrained(model_id)
        backend = getattr(tok, "backend_tokenizer", None)
        if backend is None:
            return False, "no tokenizer.json upstream and no fast tokenizer to convert from"
        dest.mkdir(parents=True, exist_ok=True)
        backend.save(str(dest / "tokenizer.json"))
    except Exception as exc:  # any conversion failure is reported, never aborts the whole sync
        return False, f"sentencepiece conversion failed: {exc.__class__.__name__}"
    # Record the SOURCE COMMIT, not the bare word "converted-from-sentencepiece". §5.4d exists so a
    # published tokens/word figure is tied to a tokenizer *version*; a literal string identifies
    # nothing and cannot be re-resolved. The conversion is deterministic given the source revision,
    # so the sha plus the marker is the honest provenance. Falls back to the marker alone only
    # if the hub cannot be reached.
    try:
        sha = HfApi().model_info(model_id).sha
        return True, f"{sha} (converted-from-sentencepiece)"
    except Exception:
        return True, "converted-from-sentencepiece (source revision unresolved)"


def sync_one(model_id: str, out_root: Path) -> tuple[bool, str]:
    """Download one tokenizer.json. Returns (ok, detail) rather than raising."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import (
        EntryNotFoundError,
        GatedRepoError,
        HfHubHTTPError,
        RepositoryNotFoundError,
    )

    dest = target_dir(out_root, model_id)
    try:
        cached = hf_hub_download(repo_id=model_id, filename="tokenizer.json")
    except GatedRepoError:
        return False, GATED_HINT.get(model_id, "gated — accept the terms and set HF_TOKEN")
    except RepositoryNotFoundError:
        return False, "repo not found — the id may have moved (ALLaM did; see §15)"
    except EntryNotFoundError:
        # ALLaM ships sentencepiece only; convert so it is not silently missing from the table
        return convert_from_sentencepiece(model_id, dest)
    except HfHubHTTPError as exc:
        return False, f"hub error: {exc.__class__.__name__}"

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, dest / "tokenizer.json")
    return True, snapshot_revision(cached)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--only", help="comma-separated aliases to sync (default: all five)")
    args = ap.parse_args()

    if os.environ.get("HF_HUB_OFFLINE") == "1":
        raise SystemExit(
            "HF_HUB_OFFLINE=1 — this script exists to populate the offline cache and cannot run "
            "inside it. Sync while online, then copy out/tokenizers/ to the air-gapped host "
            "(prime directive 1)."
        )

    wanted = TOKENIZERS
    if args.only:
        aliases = [a.strip() for a in args.only.split(",") if a.strip()]
        unknown = set(aliases) - set(TOKENIZERS)
        if unknown:
            raise SystemExit(f"unknown alias(es): {sorted(unknown)} — known: {sorted(TOKENIZERS)}")
        wanted = {a: TOKENIZERS[a] for a in aliases}

    args.out.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, dict[str, str]] = {}
    blocked: dict[str, str] = {}

    for alias, model_id in wanted.items():
        ok, detail = sync_one(model_id, args.out)
        if ok:
            resolved[alias] = {"model_id": model_id, "revision": detail}
            log.info("tokenizer_synced", alias=alias, model=model_id, revision=detail[:12])
        else:
            blocked[alias] = detail
            log.warning("tokenizer_blocked", alias=alias, model=model_id, reason=detail)

    manifest = args.out / "tokenizers.manifest.json"
    existing = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    existing.update(resolved)
    manifest.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"\n  synced {len(resolved)}/{len(wanted)} tokenizers into {args.out}")
    for alias, info in sorted(existing.items()):
        print(f"    ✓ {alias:14} {info['model_id']} @ {info['revision'][:12]}")
    for alias, reason in sorted(blocked.items()):
        print(f"    ✗ {alias:14} {reason}")
    if blocked:
        print(
            "\n  Fertility can still be measured for the synced tokenizers; the table will be "
            "incomplete until the rest land.\n"
        )
    if not existing:
        sys.exit(1)


if __name__ == "__main__":
    main()
