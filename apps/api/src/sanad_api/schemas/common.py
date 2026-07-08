"""Shared schema shapes: problem+json errors (§7.1) and the x_sanad usage block."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Problem(BaseModel):
    """RFC 9457 problem+json error body — every non-2xx response uses this shape."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class XSanad(BaseModel):
    """Sanad metadata appended to OpenAI-compatible responses (§7.1)."""

    upstream: str = Field(description="vllm | llamacpp")
    model_alias: str
    sovereign: bool
    ttft_ms: float | None = None
    tokens_per_second: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    detected_lang: str | None = Field(default=None, description="ar | en | mixed")
