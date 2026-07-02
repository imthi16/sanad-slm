"""GET /v1/telemetry/stream — SSE fan-out of edge/GPU metrics via Redis pub/sub (§7.2).

Exporters (tegrastats sidecar, DCGM bridge) publish JSON snapshots to the `sanad:telemetry`
channel; every dashboard client gets its own subscription. POST endpoint lets edge boxes
without Redis access push through the API (service token).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from sanad_api.core.security import ServiceToken
from sanad_api.db.models import TelemetrySnapshot as TelemetryRow
from sanad_api.db.session import get_session
from sanad_api.schemas.telemetry import TelemetrySnapshot

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])

CHANNEL = "sanad:telemetry"

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/stream")
async def stream(request: Request) -> EventSourceResponse:
    redis = request.app.state.redis

    async def gen() -> AsyncIterator[dict[str, str]]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if msg is None:
                    continue
                data = msg["data"]
                yield {"data": data.decode() if isinstance(data, bytes) else str(data)}
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()

    return EventSourceResponse(gen(), ping=15)


@router.post("/ingest", status_code=202)
async def ingest(
    snapshot: TelemetrySnapshot, request: Request, _: ServiceToken, session: Session
) -> dict[str, str]:
    # ServiceToken precedes Session: auth must reject before a DB session is acquired
    payload = snapshot.model_dump_json()
    await request.app.state.redis.publish(CHANNEL, payload)
    session.add(
        TelemetryRow(
            source=snapshot.source,
            ts=snapshot.ts,
            watts=snapshot.watts,
            gpu_util_pct=snapshot.gpu_util_pct,
            temp_c=snapshot.temp_c,
            tokens_per_second=snapshot.tokens_per_second,
            mem_used_gb=snapshot.mem_used_gb,
        )
    )
    await session.commit()
    return {"status": "accepted"}


async def demo_publisher(request_app_state: object, interval: float = 2.0) -> None:
    """dev-mode only: synthetic telemetry so the EdgeBoard scene works without a Jetson."""
    import math
    import time

    redis = request_app_state.redis  # type: ignore[attr-defined]
    t0 = time.monotonic()
    while True:
        t = time.monotonic() - t0
        snapshot = {
            "source": "jetson-demo",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "watts": round(10 + 4 * math.sin(t / 7), 2),
            "gpu_util_pct": round(55 + 35 * abs(math.sin(t / 11)), 1),
            "temp_c": round(48 + 6 * math.sin(t / 23), 1),
            "tokens_per_second": round(24 + 5 * math.sin(t / 5), 1),
            "mem_used_gb": round(3.1 + 0.4 * abs(math.sin(t / 13)), 2),
        }
        await redis.publish(CHANNEL, json.dumps(snapshot))
        await asyncio.sleep(interval)
