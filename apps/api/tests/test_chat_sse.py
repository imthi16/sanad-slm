"""SSE proxy chunk-integrity test (§7.4): upstream chunks pass through byte-identical,
and exactly one final x_sanad frame precedes [DONE]."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

UPSTREAM = "http://vllm.test/v1/chat/completions"

CHUNKS = [
    {
        "id": "c1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": "مرحباً"}}],
    },
    {
        "id": "c1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": " بك"}}],
    },
    {
        "id": "c1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 2},
    },
]


def sse_body() -> bytes:
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in CHUNKS]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


@respx.mock
@pytest.mark.anyio
async def test_stream_passthrough_and_final_frame(client: httpx.AsyncClient) -> None:
    respx.post(UPSTREAM).mock(
        return_value=httpx.Response(
            200, content=sse_body(), headers={"content-type": "text/event-stream"}
        )
    )

    payload = {
        "model": "sanad-bank-awq",
        "stream": True,
        "messages": [{"role": "user", "content": "ما هو الحد الأدنى للرصيد؟"}],
    }
    events: list[str] = []
    async with client.stream("POST", "/v1/chat/completions", json=payload) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                events.append(line[6:])

    # upstream chunks byte-identical (unicode preserved, no re-serialization drift)
    for original, received in zip(CHUNKS, events, strict=False):
        assert json.loads(received) == original
    assert "مرحباً" in events[0]

    # exactly one sanad.final frame with metrics, then [DONE]
    finals = [e for e in events if '"sanad.final"' in e]
    assert len(finals) == 1
    x = json.loads(finals[0])["x_sanad"]
    assert x["model_alias"] == "sanad-bank-awq"
    assert x["upstream"] == "vllm"
    assert x["detected_lang"] == "ar"
    assert x["completion_tokens"] == 2
    assert events[-1] == "[DONE]"


@respx.mock
@pytest.mark.anyio
async def test_non_streaming_augments_usage(client: httpx.AsyncClient) -> None:
    respx.post(UPSTREAM).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "r1",
                "object": "chat.completion",
                "model": "sanad-bank-awq",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            },
        )
    )
    r = await client.post(
        "/v1/chat/completions",
        json={
            "model": "sanad-bank-awq",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["x_sanad"]["upstream"] == "vllm"
    assert body["x_sanad"]["detected_lang"] == "en"
    assert body["usage"]["total_tokens"] == 6


@pytest.mark.anyio
async def test_unknown_alias_is_problem_404(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/chat/completions",
        json={
            "model": "nope",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
