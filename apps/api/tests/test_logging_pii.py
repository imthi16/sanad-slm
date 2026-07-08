from __future__ import annotations

from sanad_api.core.logging import scrub


def test_scrub_email() -> None:
    assert "user@example.ae" not in scrub("contact user@example.ae now")


def test_scrub_uae_iban() -> None:
    assert "<iban>" in scrub("transfer to AE070331234567890123456 today")


def test_scrub_emirates_id_western_and_eastern_digits() -> None:
    assert "<emirates-id>" in scrub("EID 784-1990-1234567-1")
    # Eastern Arabic digits must not slip through (§10: AR + EN regexes)
    assert "<emirates-id>" in scrub("الهوية ٧٨٤-١٩٩٠-١٢٣٤٥٦٧-١")


def test_scrub_uae_phone() -> None:
    assert "<phone>" in scrub("call +971501234567")
    assert "<phone>" in scrub("اتصل على 0501234567")


def test_clean_text_untouched() -> None:
    text = "الحد الأدنى للرصيد 3,000 درهم"
    assert scrub(text) == text
