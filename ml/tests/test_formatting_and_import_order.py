"""Two P2 failures that only surfaced with a warm GPU, pinned down so they cannot come back.

1. `formatting_func` must accept a single example as well as a batch. TRL's `_prepare_dataset`
   probes with `formatting_func(next(iter(dataset)))` before it ever maps over batches.
2. `import unsloth` must precede trl/transformers/peft in `sft.py`. Unsloth patches those at
   import time by rebinding `trl.SFTTrainer`/`trl.SFTConfig`; a name bound earlier keeps pointing
   at the unpatched class, so the run drives an Unsloth-patched model through stock TRL.

Both are checked without torch, CUDA, or weights — statically, or against a fake tokenizer.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from chat_template import formatting_func

ML_ROOT = Path(__file__).resolve().parents[1]
SFT = ML_ROOT / "train" / "sft.py"

#: Unsloth rebinds these on import, so each must be imported after it.
PATCHED_BY_UNSLOTH = {"trl", "transformers", "peft"}

CONVERSATION = [
    {"role": "user", "content": "ما هو الحد الأدنى للرصيد؟"},
    {"role": "assistant", "content": "الحد الأدنى هو ٣٠٠٠ درهم."},
]
CONVERSATION_2 = [
    {"role": "user", "content": "What is the minimum balance?"},
    {"role": "assistant", "content": "AED 3,000."},
]


class FakeTokenizer:
    """Records what it was handed, and rejects anything that is not a conversation."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def apply_chat_template(self, conversation: Any, **kwargs: Any) -> str:
        self.calls.append(conversation)
        if not isinstance(conversation, list):
            raise TypeError(f"expected a list of messages, got {type(conversation).__name__}")
        if not all(isinstance(m, dict) and "role" in m for m in conversation):
            raise TypeError("expected every element to be a {role, content} message")
        return " | ".join(f"{m['role']}:{m['content']}" for m in conversation)


def test_single_example_returns_one_string() -> None:
    """TRL's probe shape. This is the call that raised UndefinedError on 2026-07-28."""
    tok = FakeTokenizer()
    out = formatting_func(tok)({"messages": CONVERSATION})
    assert isinstance(out, str)
    assert "الحد الأدنى" in out


def test_single_example_is_not_split_into_individual_messages() -> None:
    """The regression itself: one conversation must reach the template whole, not per-message."""
    tok = FakeTokenizer()
    formatting_func(tok)({"messages": CONVERSATION})
    assert len(tok.calls) == 1, "conversation was split into separate template calls"
    assert tok.calls[0] == CONVERSATION


def test_batch_returns_a_list_of_strings() -> None:
    tok = FakeTokenizer()
    out = formatting_func(tok)({"messages": [CONVERSATION, CONVERSATION_2]})
    assert isinstance(out, list)
    assert len(out) == 2
    assert all(isinstance(s, str) for s in out)


def test_empty_messages_does_not_crash() -> None:
    assert formatting_func(FakeTokenizer())({"messages": []}) == []


def _import_order(path: Path) -> list[tuple[int, str]]:
    """(line number, root package) for every import inside the module, in source order."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name.split(".")[0]) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module.split(".")[0]))
    return sorted(found)


def test_sft_imports_unsloth_at_all() -> None:
    assert "unsloth" in {pkg for _, pkg in _import_order(SFT)}


@pytest.mark.parametrize("package", sorted(PATCHED_BY_UNSLOTH))
def test_unsloth_is_imported_before_the_packages_it_patches(package: str) -> None:
    order = _import_order(SFT)
    unsloth_line = min(line for line, pkg in order if pkg == "unsloth")
    later = [line for line, pkg in order if pkg == package]
    if not later:
        pytest.skip(f"sft.py does not import {package}")
    assert unsloth_line < min(later), (
        f"sft.py imports {package} at line {min(later)}, before unsloth at line {unsloth_line}. "
        "Unsloth patches it at import time; a name bound earlier stays unpatched and the run "
        "drives a patched model through stock TRL (ADR-0007)."
    )
