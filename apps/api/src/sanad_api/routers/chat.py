"""OpenAI-compatible chat proxy with SSE streaming + x_sanad augmentation (§7.2, §7.3).

Streaming: upstream OpenAI chunks pass through untouched; one final Sanad frame carries
ttft/tok/s/lang. Chat content is NOT persisted unless SANAD_PERSIST_CHATS=true (dev only).
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from sanad_api.core.metrics import CHAT_TOKENS
from sanad_api.core.security import RateLimited
from sanad_api.db.models import ChatUsage
from sanad_api.schemas.chat import ChatRequest
from sanad_api.schemas.common import XSanad
from sanad_api.services.inference_router import Upstream, detect_lang

log = structlog.get_logger()
router = APIRouter(tags=["chat"])


def _resolve(request: Request, alias: str) -> Upstream:
    try:
        return request.app.state.router.resolve(alias)  # type: ignore[no-any-return]
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown model alias '{alias}'") from None


def _prompt_text(req: ChatRequest) -> str:
    parts = []
    for m in req.messages:
        if isinstance(m.content, str):
            parts.append(m.content)
    return "\n".join(parts)


async def _record_usage(request: Request, x: XSanad, content: str | None) -> None:
    settings = request.app.state.settings
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return
    try:
        async with factory() as session:
            session.add(
                ChatUsage(
                    model_alias=x.model_alias,
                    upstream=x.upstream,
                    prompt_tokens=x.prompt_tokens or 0,
                    completion_tokens=x.completion_tokens or 0,
                    ttft_ms=x.ttft_ms,
                    tokens_per_second=x.tokens_per_second,
                    detected_lang=x.detected_lang,
                    content=content if settings.persist_chats and settings.mode == "dev" else None,
                )
            )
            await session.commit()
    except Exception as exc:
        log.warning("chat_usage_persist_failed", reason=str(exc))


@router.post("/v1/chat/completions", dependencies=[])
async def chat(req: ChatRequest, request: Request, _: RateLimited) -> Any:
    upstream = _resolve(request, req.model)
    settings = request.app.state.settings
    http: httpx.AsyncClient = request.app.state.http
    payload = req.model_dump(exclude_none=True)
    payload["model"] = upstream.served_name
    lang = detect_lang(_prompt_text(req))

    if not req.stream:
        start = time.perf_counter()
        try:
            r = await http.post(f"{upstream.base_url}/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"upstream {upstream.alias} unreachable: {exc}"
            ) from exc
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text[:500])
        body = r.json()
        usage = body.get("usage") or {}
        elapsed = time.perf_counter() - start
        completion = int(usage.get("completion_tokens") or 0)
        x = XSanad(
            upstream=upstream.kind,
            model_alias=upstream.alias,
            sovereign=settings.mode != "dev",
            ttft_ms=round(elapsed * 1000, 1),
            tokens_per_second=round(completion / elapsed, 2)
            if elapsed > 0 and completion
            else None,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            detected_lang=lang,
        )
        body["x_sanad"] = x.model_dump()
        CHAT_TOKENS.labels(upstream.alias, "prompt").inc(int(usage.get("prompt_tokens") or 0))
        CHAT_TOKENS.labels(upstream.alias, "completion").inc(completion)
        await _record_usage(request, x, _prompt_text(req))
        return body

    async def gen() -> AsyncIterator[dict[str, str]]:
        start = time.perf_counter()
        first_token_at: float | None = None
        completion_tokens = 0
        prompt_tokens: int | None = None
        try:
            async with http.stream(
                "POST", f"{upstream.base_url}/chat/completions", json=payload
            ) as r:
                if r.status_code >= 400:
                    detail = (await r.aread()).decode(errors="replace")[:500]
                    yield {
                        "event": "error",
                        "data": json.dumps({"status": r.status_code, "detail": detail}),
                    }
                    return
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    with_usage = None
                    with contextlib.suppress(json.JSONDecodeError):
                        with_usage = json.loads(data)
                    if with_usage:
                        if with_usage.get("choices") and with_usage["choices"][0].get(
                            "delta", {}
                        ).get("content"):
                            completion_tokens += 1  # chunk ≈ token for OSS servers
                        if u := with_usage.get("usage"):
                            prompt_tokens = u.get("prompt_tokens", prompt_tokens)
                            completion_tokens = u.get("completion_tokens", completion_tokens)
                    yield {"data": data}  # passthrough OpenAI chunks untouched
        except httpx.HTTPError as exc:
            yield {"event": "error", "data": json.dumps({"status": 502, "detail": str(exc)})}
            return

        gen_seconds = (time.perf_counter() - (first_token_at or start)) or 1e-6
        x = XSanad(
            upstream=upstream.kind,
            model_alias=upstream.alias,
            sovereign=settings.mode != "dev",
            ttft_ms=round(((first_token_at or start) - start) * 1000, 1),
            tokens_per_second=round(completion_tokens / gen_seconds, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            detected_lang=lang,
        )
        CHAT_TOKENS.labels(upstream.alias, "completion").inc(completion_tokens)
        await _record_usage(request, x, _prompt_text(req))
        yield {"data": json.dumps({"object": "sanad.final", "x_sanad": x.model_dump()})}
        yield {"data": "[DONE]"}

    return EventSourceResponse(gen(), ping=15)
