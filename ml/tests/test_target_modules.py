"""`target_modules: all-linear` must reach Unsloth as an explicit list (P2 acceptance, §5.2).

PEFT supports the `all-linear` shorthand; Unsloth's text path does not. `llama.py` does
`list(target_modules)` before PEFT sees it, so the string decomposes into its own characters and
adapter injection fails with `Target modules {'n','-','r','a','l','i','e'} not found in the base
model` — which is what killed the 2026-07-27 run after preflight had gone green.

These tests fake the module tree so the expansion is covered without torch, CUDA, or the 8 GB of
weights. The point is the *shape* of what Unsloth receives, and that is checkable on a laptop.
"""

from __future__ import annotations

import pytest
from sft import ALL_LINEAR, resolve_target_modules


class FakeLinear:
    pass


class FakeLinear4bit(FakeLinear):
    """bitsandbytes' 4-bit layer subclasses Linear — the form every layer takes under QLoRA."""


class FakeLayerNorm:
    pass


class FakeEmbedding:
    pass


class FakeModel:
    """Minimal stand-in exposing the one method the resolver uses."""

    def __init__(self, modules: dict[str, object]) -> None:
        self._modules = modules

    def named_modules(self) -> list[tuple[str, object]]:
        return list(self._modules.items())


def qwen3_like(layers: int = 2) -> FakeModel:
    """The real Qwen3-4B leaf inventory, verified against its safetensors index."""
    tree: dict[str, object] = {
        "model.embed_tokens": FakeEmbedding(),
        "model.norm": FakeLayerNorm(),
        "lm_head": FakeLinear(),
    }
    for i in range(layers):
        for proj in ("q_proj", "k_proj", "v_proj", "o_proj"):
            tree[f"model.layers.{i}.self_attn.{proj}"] = FakeLinear4bit()
        for proj in ("gate_proj", "up_proj", "down_proj"):
            tree[f"model.layers.{i}.mlp.{proj}"] = FakeLinear4bit()
        for norm in ("input_layernorm", "post_attention_layernorm", "q_norm", "k_norm"):
            tree[f"model.layers.{i}.{norm}"] = FakeLayerNorm()
    return FakeModel(tree)


QWEN3_PROJECTIONS = [
    "down_proj",
    "gate_proj",
    "k_proj",
    "o_proj",
    "q_proj",
    "up_proj",
    "v_proj",
]


def test_all_linear_expands_to_the_seven_qwen3_projections() -> None:
    assert resolve_target_modules(ALL_LINEAR, qwen3_like()) == QWEN3_PROJECTIONS


def test_expansion_never_returns_the_shorthands_characters() -> None:
    """The exact 2026-07-27 failure: the string iterated into a character set."""
    resolved = resolve_target_modules(ALL_LINEAR, qwen3_like())
    assert set(resolved) & set(ALL_LINEAR) == set(), "expansion leaked single characters"
    assert all(len(name) > 1 for name in resolved)


def test_embedding_and_output_head_are_excluded() -> None:
    """PEFT's shorthand excludes both; on Qwen3 they are tied, so adapting one moves the other."""
    resolved = resolve_target_modules(ALL_LINEAR, qwen3_like())
    assert "lm_head" not in resolved
    assert "embed_tokens" not in resolved


def test_norms_are_not_adapted() -> None:
    assert not [name for name in resolve_target_modules(ALL_LINEAR, qwen3_like()) if "norm" in name]


def test_explicit_list_passes_through_untouched() -> None:
    explicit = ["q_proj", "v_proj"]
    assert resolve_target_modules(explicit, qwen3_like()) == explicit


def test_unknown_bare_string_is_rejected_loudly() -> None:
    """A regex or typo must not reach Unsloth to be silently shredded into characters."""
    with pytest.raises(SystemExit, match="character-by-character"):
        resolve_target_modules("all-lienar", qwen3_like())


def test_model_with_no_linear_layers_is_refused() -> None:
    empty = FakeModel({"model.norm": FakeLayerNorm(), "model.embed_tokens": FakeEmbedding()})
    with pytest.raises(SystemExit, match="matched no linear modules"):
        resolve_target_modules(ALL_LINEAR, empty)
