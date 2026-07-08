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
