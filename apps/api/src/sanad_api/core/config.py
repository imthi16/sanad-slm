"""Canonical settings shape (CLAUDE.md §4). One env var rules them all: SANAD_MODE."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SANAD_", env_file=".env")

    mode: Literal["dev", "sovereign", "edge"] = "dev"
    vllm_base_url: str = "http://vllm:8000/v1"
    llamacpp_base_url: str = "http://llamacpp:8080/v1"
    database_url: str = "postgresql+asyncpg://sanad:sanad@postgres:5432/sanad"
    redis_url: str = "redis://redis:6379/0"
    registry_s3_endpoint: str = "http://minio:9000"
    registry_bucket: str = "sanad-models"
    registry_access_key: str = "sanad"
    registry_secret_key: str = "sanad-secret"
    allow_external_judges: bool = False  # forced False when mode != "dev"
    cors_origins: list[str] = ["http://localhost:5173"]

    # sovereign posture: chat content is NOT persisted by default (§7.3)
    persist_chats: bool = False
    # bearer token for machine ingestion (eval-job → /v1/eval/runs/{id}/ingest)
    service_token: str = "change-me-in-sops"
    # rate limit (token bucket): per-IP in dev, per-key in prod
    rate_limit_rps: float = 5.0
    rate_limit_burst: int = 20
    # local dir with pre-synced tokenizer.json files for the fertility endpoint
    tokenizers_dir: str = "/models/tokenizers"
    fertility_report_path: str = "/reports/fertility.json"
    upstream_health_interval_s: float = 15.0

    @model_validator(mode="after")
    def _sovereign_forces(self) -> Settings:
        if self.mode != "dev":
            # zero-egress modes can never call external judges (prime directive 1)
            object.__setattr__(self, "allow_external_judges", False)
        return self

    @property
    def egress_allowed(self) -> bool:
        return self.mode == "dev"
