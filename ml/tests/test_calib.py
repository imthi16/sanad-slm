"""The P3 calibration and PPL holdout must be bilingual and disjoint (§5.3).

`quantize/awq.py` refuses a calibration set under 40% Arabic *characters*, because
English-calibrated quantization silently degrades Arabic — the failure mode §5.3 calls the most
common one. And a perplexity gate scored on calibration data cannot detect the very regression it
exists to catch, so the two sets must not overlap.
"""

from __future__ import annotations

import pytest


def _rec(idx: int, lang: str, text: str) -> dict[str, object]:
    return {
        "id": f"fixture-{lang}-{idx:06d}",
        "messages": [
            {"role": "user", "content": text},
            {"role": "assistant", "content": text},
        ],
        "lang": lang,
        "domain": ["banking.compliance"],
        "provenance": "native",
        "source": {"name": "FIXTURE", "url": "local:x", "license": "Apache-2.0"},
        "pii_checked": True,
        "split": "train",
    }


def _pool(n: int = 600) -> list[dict[str, object]]:
    """60/30/10 ar/en/mixed, with the English records deliberately far longer."""
    out: list[dict[str, object]] = []
    for i in range(n):
        if i % 10 < 6:
            out.append(_rec(i, "ar", "شروط الحساب والامتثال " * 2))
        elif i % 10 < 9:
            # ~5x the characters: this is what makes a record-count split miss the char floor
            out.append(_rec(i, "en", "account compliance requirements and documentation " * 10))
        else:
            out.append(_rec(i, "mixed", "حساب compliance رصيد documentation"))
    return out


def test_calibration_clears_the_char_floor_not_just_the_record_count() -> None:
    from calib import arabic_char_ratio, pick_bilingual

    pool = _pool()
    picked = pick_bilingual(pool, 200, target_ratio=0.50, seed=3407)

    assert len(picked) == 200
    # the gate awq.py applies, on the set this produces
    assert arabic_char_ratio(picked) >= 0.40

    # a naive record-count majority would NOT have cleared it, which is the point of the helper
    naive = [r for r in pool if r["lang"] == "ar"][:100] + [r for r in pool if r["lang"] == "en"][
        :100
    ]
    assert arabic_char_ratio(naive) < 0.40


def test_calibration_stays_bilingual_rather_than_all_arabic() -> None:
    """All-Arabic calibration is as wrong as all-English — §5.3 asks for bilingual."""
    from calib import pick_bilingual

    picked = pick_bilingual(_pool(), 200, target_ratio=0.50, seed=3407)
    langs = {str(r.get("lang")) for r in picked}
    assert "en" in langs or "mixed" in langs, f"no Latin-script records selected: {langs}"


def test_calibration_selection_is_deterministic() -> None:
    from calib import pick_bilingual

    pool = _pool()
    a = pick_bilingual(pool, 150, 0.5, 3407)
    b = pick_bilingual(pool, 150, 0.5, 3407)
    assert [r["id"] for r in a] == [r["id"] for r in b]
    c = pick_bilingual(pool, 150, 0.5, 999)
    assert [r["id"] for r in c] != [r["id"] for r in a]


def test_calib_and_ppl_holdout_cannot_overlap() -> None:
    """Drawn from train and val respectively, so disjointness is structural."""
    from calib import pick_bilingual

    train = _pool(400)
    val = [_rec(10_000 + i, "ar" if i % 2 else "en", "نص held out text") for i in range(80)]
    calib = pick_bilingual(train, 200, 0.5, 3407)
    heldout = pick_bilingual(val, 60, 0.5, 3408)
    assert not {r["id"] for r in calib} & {r["id"] for r in heldout}


def test_pick_bilingual_never_exceeds_the_pool() -> None:
    from calib import pick_bilingual

    picked = pick_bilingual(_pool(30), 500, 0.5, 3407)
    assert len(picked) == 30  # asks for more than exists → returns what exists, does not hang


@pytest.mark.parametrize("ratio", [0.0, 1.0])
def test_arabic_char_ratio_extremes(ratio: float) -> None:
    from calib import arabic_char_ratio

    lang, text = ("en", "pure latin text") if ratio == 0.0 else ("ar", "نص عربي فقط")
    assert abs(arabic_char_ratio([_rec(1, lang, text)]) - ratio) < 0.01
