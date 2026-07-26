"""The data-gate must block a planted non-commercial record (P1 acceptance, §13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_curate_pii_scan_catches_uae_patterns() -> None:
    from curate_bank import pii_scan

    assert pii_scan("تواصل معي على mohamed@example.com")
    assert pii_scan("My IBAN is AE070331234567890123456")
    assert pii_scan("رقم الهوية 784-1990-1234567-1")
    assert pii_scan("call me on +971501234567")
    assert not pii_scan("الحد الأدنى للرصيد 3,000 درهم")


def test_curate_template_requires_citation_and_reviewer() -> None:
    from curate_bank import validate_draft

    draft = {"question": "q", "answer": "a", "domain": "banking.retail"}
    errors = validate_draft(draft, "t.yaml[0]")
    joined = "\n".join(errors)
    assert "citation" in joined and "reviewer" in joined


def test_curate_synthetic_draft_needs_no_reviewer() -> None:
    """A machine-drafted pair has no human attestation yet — requiring one would force a lie."""
    from curate_bank import validate_draft

    draft = {
        "question": "q",
        "answer": "a",
        "citation": "CBUAE Rulebook, Art. 8",
        "domain": "banking.retail",
        "provenance": "synthetic",
    }
    assert validate_draft(draft, "t.yaml[0]") == []


def test_curate_rejects_reviewer_on_non_native_draft() -> None:
    """A reviewed pair IS native; carrying both would let synthetic text inherit the claim."""
    from curate_bank import validate_draft

    draft = {
        "question": "q",
        "answer": "a",
        "citation": "CBUAE Rulebook, Art. 8",
        "domain": "banking.retail",
        "provenance": "synthetic",
        "reviewer": "MO",
    }
    joined = "\n".join(validate_draft(draft, "t.yaml[0]"))
    assert "reviewer" in joined and "native" in joined


def test_curate_record_preserves_synthetic_provenance() -> None:
    """Provenance must survive into the record — MANIFEST's split is computed from it."""
    from curate_bank import to_record

    rec = to_record(
        {
            "question": "q",
            "answer": "a",
            "citation": "CBUAE Rulebook, Art. 8",
            "domain": "banking.retail",
            "lang": "en",
            "provenance": "synthetic",
        },
        7,
    )
    assert rec["provenance"] == "synthetic"
    assert rec["id"] == "bank-syn-en-000007"
    assert "reviewer" not in rec["source"]


def test_gate_blocks_planted_noncommercial_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import _lib
    import manifest as manifest_mod

    processed = tmp_path / "processed"
    processed.mkdir()
    planted = {
        "id": "quarantine-ar-000001",
        "messages": [{"role": "user", "content": "س"}, {"role": "assistant", "content": "ج"}],
        "lang": "ar",
        "domain": ["general"],
        "provenance": "native",
        "source": {"name": "AraFinNews", "license": "non-commercial"},
        "pii_checked": True,
        "split": "train",
    }
    (processed / "shard.jsonl").write_text(
        json.dumps(planted, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    manifest_yaml = tmp_path / "MANIFEST.yaml"
    manifest_yaml.write_text(
        "profile: commercial\n"
        "allowed_licenses: [Apache-2.0, CC-BY-4.0, MIT]\n"
        "sources:\n"
        "  - {name: AraFinNews, url: local:data/quarantine/, license: non-commercial}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(manifest_mod, "PROCESSED", processed)
    monkeypatch.setattr(manifest_mod, "MANIFEST_PATH", manifest_yaml)
    monkeypatch.setattr(_lib, "MANIFEST_PATH", manifest_yaml)

    with pytest.raises(SystemExit, match="data-gate FAILED"):
        manifest_mod.gate("commercial")


def test_train_config_revision_must_be_a_commit_sha(tmp_path: Path) -> None:
    """The reproducibility gate rejects anything that can move (prime directive 4).

    It previously matched only the literal placeholder, so `revision: main` — or a tag, which
    upstream is free to repoint — sailed through and a rerun could silently train against
    different weights.
    """
    from sft import load_config

    def cfg_with(revision: str) -> Path:
        p = tmp_path / f"cfg-{abs(hash(revision))}.yaml"
        p.write_text(f'base_model: Qwen/Qwen3-4B-Instruct-2507\nrevision: "{revision}"\n')
        return p

    pinned = "cdbee75f17c01a7cc42f958dc650907174af0554"
    assert load_config(cfg_with(pinned))["revision"] == pinned

    for movable in ("<pin-hf-commit-sha>", "main", "v0.4.12", pinned.upper(), pinned[:39], ""):
        with pytest.raises(SystemExit, match="commit sha"):
            load_config(cfg_with(movable))


def _corpus(n: int) -> list[dict[str, object]]:
    """A schema-valid corpus with the 60/30/10 ar/en/mixed shape the curation targets."""
    out = []
    for i in range(n):
        lang = "ar" if i % 10 < 6 else ("en" if i % 10 < 9 else "mixed")
        text = f"سؤال {i}" if lang != "en" else f"question {i}"
        out.append(
            {
                "id": f"fixture-{lang}-{i:06d}",
                "messages": [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": f"{text} ."},
                ],
                "lang": lang,
                "domain": ["banking.retail"],
                "provenance": "native",
                "source": {"name": "FIXTURE", "url": "local:x", "license": "Apache-2.0"},
                "pii_checked": True,
                "split": "train",
            }
        )
    return out


def test_split_is_deterministic_and_stratified() -> None:
    """sft.py reads these shards, so an unstable or skewed split silently ruins comparability."""
    from split import assign

    corpus = _corpus(1000)
    train_a, val_a = assign(corpus, 0.05, 3407)
    train_b, val_b = assign(corpus, 0.05, 3407)

    # same seed, same corpus → byte-identical partition
    assert [r["id"] for r in val_a] == [r["id"] for r in val_b]
    assert [r["id"] for r in train_a] == [r["id"] for r in train_b]

    # partition, not a sample: nothing lost, nothing shared, labels set
    assert len(train_a) + len(val_a) == len(corpus)
    assert not {r["id"] for r in train_a} & {r["id"] for r in val_a}
    assert {r["split"] for r in train_a} == {"train"}
    assert {r["split"] for r in val_a} == {"val"}

    # val mirrors train per language, so held-out loss speaks for the code-switching case too
    for lang in ("ar", "en", "mixed"):
        share = sum(r["lang"] == lang for r in val_a) / len(val_a)
        expected = sum(r["lang"] == lang for r in corpus) / len(corpus)
        assert abs(share - expected) < 0.05, f"{lang}: val {share:.3f} vs corpus {expected:.3f}"

    # a different seed must actually move the partition
    _, val_c = assign(corpus, 0.05, 1234)
    assert [r["id"] for r in val_c] != [r["id"] for r in val_a]


def test_split_keeps_singleton_strata_in_train() -> None:
    """A stratum of one cannot be held out — that would remove its only training example."""
    from split import assign

    corpus = [
        *_corpus(20),
        {
            "id": "fixture-solo-000001",
            "messages": [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}],
            "lang": "ar",
            "domain": ["general"],
            "provenance": "synthetic",
            "source": {"name": "FIXTURE", "url": "local:x", "license": "MIT"},
            "pii_checked": True,
            "split": "train",
        },
    ]
    train, val = assign(corpus, 0.5, 3407)
    assert "fixture-solo-000001" in {r["id"] for r in train}
    assert "fixture-solo-000001" not in {r["id"] for r in val}
