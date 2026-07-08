"""sanad-api entrypoint — lifespan wiring per §7.3."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.exceptions import HTTPException as StarletteHTTPException

from sanad_api import __version__
from sanad_api.core.config import Settings
from sanad_api.core.logging import configure_logging
from sanad_api.core.metrics import instrument
from sanad_api.core.security import SecurityHeadersMiddleware
from sanad_api.db.session import make_engine, make_session_factory
from sanad_api.routers import chat, evals, health, models, registry, telemetry, tokenize
from sanad_api.services.inference_router import ModelRouter

log = structlog.get_logger()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = Settings()
    configure_logging()
    app.state.settings = s
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5))

    app.state.engine = make_engine(s.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.redis = Redis.from_url(s.redis_url)

    app.state.router = ModelRouter(s, app.state.http)
    app.state.router.start()

    demo_task: asyncio.Task[None] | None = None
    if s.mode == "dev":
        from sanad_api.routers.telemetry import demo_publisher

        demo_task = asyncio.create_task(demo_publisher(app.state), name="telemetry-demo")

    log.info("startup", mode=s.mode, egress_allowed=s.egress_allowed, version=__version__)
    yield

    if demo_task:
        demo_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await demo_task
    await app.state.router.stop()
    await app.state.http.aclose()
    await app.state.redis.aclose()
    await app.state.engine.dispose()


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="sanad-api", version=__version__, lifespan=lifespan)

    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.mode != "dev")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    instrument(app)

    for r in (chat, models, evals, telemetry, tokenize, registry, health):
        app.include_router(r.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # problem+json error shape (§7.1)
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": exc.detail if isinstance(exc.detail, str) else "error",
                "status": exc.status_code,
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": "validation error",
                "status": 422,
                "detail": str(exc.errors()[:5]),
                "instance": str(request.url.path),
            },
        )

    return app


app = create_app()
