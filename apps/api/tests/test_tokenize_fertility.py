"""Fertility endpoint + service: live tokenization with a real (tiny) tokenizer (§5.4d, §7.2)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from sanad_api.services.fertility import KNOWN_TOKENIZERS, load_static_report

BILINGUAL = "افتح حساب current account"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _write_mini_tokenizer(root: Path, alias: str) -> None:
    """A real tokenizer.json (WordLevel + Whitespace) so offsets/segments are exercised."""
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace

    words = BILINGUAL.split()
    vocab = {w: i for i, w in enumerate(dict.fromkeys(words))}
    vocab["[UNK]"] = len(vocab)
    tok = Tokenizer(WordLevel(vocab, unk_token="[UNK]"))
    tok.pre_tokenizer = Whitespace()
    target = root / KNOWN_TOKENIZERS[alias]
    target.mkdir(parents=True)
    tok.save(str(target / "tokenizer.json"))


@pytest.mark.anyio
async def test_fertility_measures_segments_and_cost(
    client: httpx.AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    _write_mini_tokenizer(tmp_path, "qwen3")  # the other four stay missing → skipped gracefully
    app.state.settings.tokenizers_dir = str(tmp_path)

    r = await client.post("/v1/tokenize/fertility", json={"text": BILINGUAL})
    assert r.status_code == 200
    body = r.json()
    assert body["detected_lang"] == "mixed"
    assert body["text_words"] == 4
    assert set(body["tokenizers"]) == {"qwen3"}

    qwen = body["tokenizers"]["qwen3"]
    assert qwen["tokens"] == 4
    assert qwen["tokens_per_word"] == pytest.approx(1.0)
    assert qwen["cost_vs_best"] == pytest.approx(1.0)  # only tokenizer ⇒ best
    scripts = {s["script"] for s in qwen["segments"]}
    assert scripts == {"ar", "en"}
    assert all(BILINGUAL[s["start"] : s["end"]] == s["text"] for s in qwen["segments"])


@pytest.mark.anyio
async def test_fertility_503_when_no_tokenizers(
    client: httpx.AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    app.state.settings.tokenizers_dir = str(tmp_path / "empty")
    r = await client.post("/v1/tokenize/fertility", json={"text": "hello"})
    assert r.status_code == 503


@pytest.mark.anyio
async def test_fertility_report_404_then_200(
    client: httpx.AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    report_path = tmp_path / "fertility.json"
    app.state.settings.fertility_report_path = str(report_path)

    r = await client.get("/v1/tokenize/fertility/report")
    assert r.status_code == 404

    report = {"corpora": {"msa_news_10k": {"qwen3": 1.9}}}
    report_path.write_text(json.dumps(report), encoding="utf-8")
    r = await client.get("/v1/tokenize/fertility/report")
    assert r.status_code == 200
    assert r.json() == report


def test_load_static_report_missing_returns_none(tmp_path: Path) -> None:
    assert load_static_report(str(tmp_path / "nope.json")) is None
