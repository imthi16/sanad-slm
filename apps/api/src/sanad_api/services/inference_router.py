"""ModelRouter (§6.3): model_alias → {upstream_kind, base_url, served_name}.

The API never hardcodes upstreams. Aliases come from settings defaults + registry artifacts;
health-checks run every 15 s and are exposed via /v1/models. Unknown alias → 404 problem.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass, field

import httpx
import structlog

from sanad_api.core.config import Settings
from sanad_api.core.metrics import UPSTREAM_UP

log = structlog.get_logger()

_ARABIC_RE = re.compile(r"[؀-ۿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def detect_lang(text: str) -> str:
    """Cheap script-based detection for the x_sanad block (ar | en | mixed)."""
    ar = len(_ARABIC_RE.findall(text))
    la = len(_LATIN_RE.findall(text))
    if not ar and not la:
        return "en"
    if ar and la and min(ar, la) / (ar + la) > 0.15:
        return "mixed"
    return "ar" if ar >= la else "en"


@dataclass
class Upstream:
    alias: str
    kind: str  # "vllm" | "llamacpp"
    base_url: str
    served_name: str
    quant_format: str | None = None
    license: str | None = None
    healthy: bool = field(default=False)


class ModelRouter:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._upstreams: dict[str, Upstream] = {}
        self._task: asyncio.Task[None] | None = None
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        self.register(
            Upstream(
                alias="sanad-bank-awq",
                kind="vllm",
                base_url=self._settings.vllm_base_url,
                served_name="sanad-bank-awq",
                quant_format="awq-w4a16",
                license="Apache-2.0",
            )
        )
        self.register(
            Upstream(
                alias="sanad-bank-gguf",
                kind="llamacpp",
                base_url=self._settings.llamacpp_base_url,
                served_name="sanad-bank-gguf",
                quant_format="gguf-q4_k_m",
                license="Apache-2.0",
            )
        )

    def register(self, upstream: Upstream) -> None:
        self._upstreams[upstream.alias] = upstream

    def resolve(self, alias: str) -> Upstream:
        up = self._upstreams.get(alias)
        if up is None:
            raise KeyError(alias)
        return up

    def list(self) -> list[Upstream]:
        return list(self._upstreams.values())

    @property
    def any_healthy(self) -> bool:
        return any(u.healthy for u in self._upstreams.values())

    async def _check_one(self, up: Upstream) -> None:
        # vLLM: GET /health at server root; llama.cpp: GET /health as well
        root = up.base_url.removesuffix("/v1")
        try:
            r = await self._http.get(f"{root}/health", timeout=5)
            up.healthy = r.status_code == 200
        except httpx.HTTPError:
            up.healthy = False
        UPSTREAM_UP.labels(up.alias).set(1 if up.healthy else 0)

    async def check_now(self) -> None:
        await asyncio.gather(*(self._check_one(u) for u in self._upstreams.values()))

    async def _loop(self) -> None:
        while True:
            await self.check_now()
            await asyncio.sleep(self._settings.upstream_health_interval_s)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="model-router-health")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
