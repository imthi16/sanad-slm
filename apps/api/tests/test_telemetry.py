"""Telemetry: SSE stream fan-out, machine ingest, dev demo publisher (§6.2, §7.2)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sanad_api.db.models import TelemetrySnapshot as TelemetryRow
from sanad_api.routers.telemetry import CHANNEL, demo_publisher


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakePubSub:
    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self.unsubscribed = False

    async def subscribe(self, channel: str) -> None:
        self.channel = channel

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed = True

    async def aclose(self) -> None:
        pass

    async def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float | None = None,  # noqa: ASYNC109 — mirrors redis-py's pubsub signature
    ) -> dict[str, Any] | None:
        if self._messages:
            return {"type": "message", "data": self._messages.pop(0).encode()}
        await asyncio.sleep(0.01)
        return None


class _FakeRedis:
    def __init__(self, stream_messages: list[str] | None = None) -> None:
        self.published: list[tuple[str, str]] = []
        self._stream_messages = stream_messages or []

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub(self._stream_messages)


@pytest.mark.anyio
async def test_stream_relays_pubsub_messages(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = {"source": "edge-01", "watts": 12.5}
    app.state.redis = _FakeRedis(stream_messages=[json.dumps(snapshot)])

    # ASGITransport never emits http.disconnect; end the stream after a few loop turns
    calls = {"n": 0}

    async def _disconnect_after_two(self: Any) -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    monkeypatch.setattr("starlette.requests.Request.is_disconnected", _disconnect_after_two)

    lines: list[str] = []
    async with client.stream("GET", "/v1/telemetry/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        async for line in r.aiter_lines():
            lines.append(line)

    data_lines = [ln for ln in lines if ln.startswith("data:") and "watts" in ln]
    assert data_lines, f"no telemetry data frame relayed; got: {lines}"
    assert json.loads(data_lines[0].split("data:", 1)[1].strip()) == snapshot


@pytest.mark.anyio
async def test_ingest_requires_token(
    client: httpx.AsyncClient, app: FastAPI, db: async_sessionmaker[AsyncSession]
) -> None:
    app.state.redis = _FakeRedis()
    r = await client.post(
        "/v1/telemetry/ingest",
        json={"source": "edge-01", "ts": "2026-07-15T00:00:00Z"},
        headers={"Authorization": "Bearer nope"},
    )
    assert r.status_code == 401


@pytest.mark.anyio
async def test_ingest_publishes_and_persists(
    client: httpx.AsyncClient, app: FastAPI, db: async_sessionmaker[AsyncSession]
) -> None:
    fake = _FakeRedis()
    app.state.redis = fake
    r = await client.post(
        "/v1/telemetry/ingest",
        json={"source": "edge-01", "ts": "2026-07-15T00:00:00Z", "watts": 11.2, "temp_c": 51.0},
        headers={"Authorization": f"Bearer {app.state.settings.service_token}"},
    )
    assert r.status_code == 202

    channel, payload = fake.published[0]
    assert channel == CHANNEL
    assert json.loads(payload)["watts"] == 11.2

    async with db() as session:
        rows = (await session.execute(select(TelemetryRow))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == "edge-01"
    assert rows[0].watts == pytest.approx(11.2)


@pytest.mark.anyio
async def test_demo_publisher_emits_valid_snapshots() -> None:
    class _State:
        redis = _FakeRedis()

    state = _State()
    task = asyncio.create_task(demo_publisher(state, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert state.redis.published
    channel, payload = state.redis.published[0]
    assert channel == CHANNEL
    snapshot = json.loads(payload)
    assert snapshot["source"] == "edge-demo"
    assert {"watts", "gpu_util_pct", "temp_c", "tokens_per_second"} <= set(snapshot)
