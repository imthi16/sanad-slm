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
    """TRL SFTTrainer `formatting_func` over record-schema rows.

    Handles both shapes TRL passes, because it passes both. `_prepare_dataset` first probes with a
    *single* example — `formatting_func(next(iter(dataset)))`, where `messages` is one
    conversation, a list of `{role, content}` dicts — and only afterwards maps over batches, where
    `messages` is a list of conversations. Assuming the batched shape made the probe iterate one
    conversation's individual messages and hand a bare dict to the chat template, which failed as
    `jinja2.UndefinedError: dict object has no element 0` rather than as anything self-describing.

    Disambiguated on the first element rather than on a `batched` flag: TRL does not pass one, and
    the two shapes are distinguishable — a conversation's elements are dicts, a batch's are lists.
    """

    def _fmt(row: dict[str, Any]) -> str | list[str]:
        messages = row["messages"]
        if messages and isinstance(messages[0], dict):
            return format_for_sft(tokenizer, messages)  # one conversation → one string
        return [format_for_sft(tokenizer, conv) for conv in messages]

    return _fmt


def assert_non_thinking(rendered: str) -> None:
    """Guard: a template drift that reintroduces thinking mode must fail loudly."""
    if "<think>" in rendered and "</think>" not in rendered.split("<think>", 1)[1][:16]:
        raise ValueError(
            "chat template emitted an open <think> block — enable_thinking=False regressed"
        )
