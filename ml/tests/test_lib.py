"""Unit tests for the data-pipeline core (§11: schema validators + manifest gen covered)."""

from __future__ import annotations

from typing import Any

import pytest
from _lib import dedup_key, nfc, script_ratios, validate_records


def test_dedup_key_collapses_arabic_variants() -> None:
    # alef variants, ta marbuta, diacritics and tatweel must collide
    assert dedup_key("إِدَارَةُ الْمَخَاطِرِ") == dedup_key("اداره المخاطر")
    assert dedup_key("مصـــرف") == dedup_key("مصرف")


def test_dedup_key_preserves_distinct_content() -> None:
    assert dedup_key("حساب توفير") != dedup_key("حساب جاري")


def test_nfc_is_canonical_not_lossy() -> None:
    # NFC must not strip diacritics — raw SFT text keeps them (§5.1)
    assert "َ" in nfc("كَتَبَ")


def test_script_ratios() -> None:
    ar, la = script_ratios("مرحبا hello")
    assert ar == pytest.approx(5 / 10)
    assert la == pytest.approx(5 / 10)
    assert script_ratios("12345") == (0.0, 0.0)


def _valid_record() -> dict[str, Any]:
    return {
        "id": "bank-ar-000001",
        "messages": [
            {"role": "user", "content": "سؤال"},
            {"role": "assistant", "content": "جواب"},
        ],
        "lang": "ar",
        "domain": ["banking.retail"],
        "provenance": "native",
        "source": {"name": "sanad-bank-pairs", "license": "CC-BY-4.0"},
        "pii_checked": True,
        "split": "train",
    }


def test_schema_accepts_valid_record() -> None:
    validate_records([_valid_record()])


def test_schema_rejects_bad_provenance() -> None:
    rec = _valid_record()
    rec["provenance"] = "scraped"
    with pytest.raises(SystemExit):
        validate_records([rec])


def test_schema_rejects_missing_license() -> None:
    rec = _valid_record()
    del rec["source"]["license"]
    with pytest.raises(SystemExit):
        validate_records([rec])
