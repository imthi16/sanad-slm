"""OpenAI Chat Completions dialect (§3.2 contract) — passthrough-compatible, minimally typed."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sanad_api.schemas.common import XSanad


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")  # tool calls etc. pass through untouched

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # unknown OpenAI params proxied verbatim

    model: str = Field(description="Sanad model alias, e.g. sanad-bank-awq")
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """Non-streaming response: upstream body + x_sanad augmentation."""

    model_config = ConfigDict(extra="allow")

    id: str
    object: str = "chat.completion"
    model: str
    choices: list[dict[str, Any]]
    usage: ChatUsage | None = None
    x_sanad: XSanad | None = None
