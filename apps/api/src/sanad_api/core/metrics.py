"""Prometheus metrics: sanad_api_request_seconds{route,method,status} on every route (§7.1)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

REQUEST_SECONDS = Histogram(
    "sanad_api_request_seconds",
    "API request latency",
    labelnames=("route", "method", "status"),
    buckets=(0.005, 0.025, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 60.0),
)
UPSTREAM_UP = Gauge(
    "sanad_upstream_up", "Inference upstream health (1=healthy)", labelnames=("upstream",)
)
CHAT_TOKENS = Counter(
    "sanad_chat_tokens_total",
    "Tokens proxied through /v1/chat/completions",
    labelnames=("model", "kind"),  # kind: prompt | completion
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        REQUEST_SECONDS.labels(route_path, request.method, str(response.status_code)).observe(
            time.perf_counter() - start
        )
        return response


def mount_metrics(app: FastAPI) -> None:
    @app.get("/metrics", include_in_schema=False)
    async def metrics(_: Request) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def instrument(app: FastAPI, **_: Any) -> None:
    app.add_middleware(MetricsMiddleware)
    mount_metrics(app)
