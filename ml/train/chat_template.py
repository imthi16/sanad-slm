"""Qwen3 chat-template application — non-thinking mode (enable_thinking=False).

We ship the low-latency non-thinking mode (§5.2): the template must never emit <think> blocks
during SFT formatting, and generation prompts close with an empty think tag per Qwen3 spec.
"""

from __future__ import annotations

from typing import Any, Protocol


class _Tokenizer(Protocol):
    def apply_chat_template(self, conversation: Any, **kwargs: Any) -> str: ...


def format_for_sft(tokenizer: _Tokenizer, messages: list[dict[str, str]]) -> str:
    """Render a full conversation for SFT (no generation prompt)."""
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
        enable_thinking=False,
    )


def format_for_generation(tokenizer: _Tokenizer, messages: list[dict[str, str]]) -> str:
    """Render a prompt for inference-time generation (eval answering, judges)."""
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )


def formatting_func(tokenizer: _Tokenizer) -> Any:
    """TRL SFTTrainer `formatting_func` over record-schema rows."""

    def _fmt(batch: dict[str, list[Any]]) -> list[str]:
        return [format_for_sft(tokenizer, msgs) for msgs in batch["messages"]]

    return _fmt


def assert_non_thinking(rendered: str) -> None:
    """Guard: a template drift that reintroduces thinking mode must fail loudly."""
    if "<think>" in rendered and "</think>" not in rendered.split("<think>", 1)[1][:16]:
        raise ValueError(
            "chat template emitted an open <think> block — enable_thinking=False regressed"
        )
