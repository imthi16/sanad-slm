from __future__ import annotations

from langid import detect_lang


def test_detect_pure_arabic() -> None:
    assert detect_lang("ما هي متطلبات فتح حساب توفير في البنك؟") == "ar"


def test_detect_pure_english() -> None:
    assert detect_lang("What is the minimum balance requirement?") == "en"


def test_detect_code_switch_mixed() -> None:
    # both scripts > 15% → mixed (§5.1)
    assert detect_lang("أبغى أفتح current account في البنك please") == "mixed"


def test_light_latin_stays_arabic() -> None:
    # a lone Latin acronym must not flip the tag
    text = "ما المقصود بمتطلبات KYC في المصرف؟ وهل تنطبق على جميع الحسابات المصرفية الجديدة؟"
    assert detect_lang(text) == "ar"


def test_minhash_near_duplicates_collide() -> None:
    from dedup import JACCARD_THRESHOLD, minhash

    a = minhash("يخضع حساب التوفير لمعدل فائدة سنوي قدره 2.75% يحتسب يوميا")
    b = minhash("يخضع حساب التوفير لمعدل فائدة سنوي قدره 2.75% يُحتسب يومياً")
    assert a.jaccard(b) >= JACCARD_THRESHOLD


def test_minhash_distinct_texts_do_not_collide() -> None:
    from dedup import JACCARD_THRESHOLD, minhash

    a = minhash("شروط فتح الحساب الجاري للشركات الصغيرة والمتوسطة في الدولة")
    b = minhash("متطلبات الإبلاغ عن المعاملات المشبوهة وفق نظام مواجهة غسل الأموال")
    assert a.jaccard(b) < JACCARD_THRESHOLD
