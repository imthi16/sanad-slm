from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from sanad_api.core.config import Settings
from sanad_api.main import create_app
from sanad_api.services.inference_router import ModelRouter


@pytest.fixture
def settings() -> Settings:
    return Settings(
        mode="dev", vllm_base_url="http://vllm.test/v1", llamacpp_base_url="http://llamacpp.test/v1"
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """App wired for tests: real router resolution, no DB/Redis (degraded-mode paths)."""
    application = create_app()
    application.router.lifespan_context = _noop_lifespan  # type: ignore[assignment]
    application.state.settings = settings
    application.state.http = httpx.AsyncClient(timeout=10)
    application.state.router = ModelRouter(settings, application.state.http)
    yield application
    await application.state.http.aclose()


@contextlib.asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
