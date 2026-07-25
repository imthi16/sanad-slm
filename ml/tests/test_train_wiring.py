"""The training path's late-bound imports must resolve (P2 acceptance, §13).

`sft.py` defers its heavy imports into `main()`, and pulls `write_lineage` in only *after* the
run finishes — hours in. A renamed symbol there fails at the one moment where failure costs the
whole run, and neither ruff nor mypy catches it, because the import sits inside a function body
guarded by dependencies CI does not install.

These tests read the import statements statically and check the symbols against the real modules,
so the CUDA stack is never needed to prove the wiring holds.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
#: modules that live in this repo and are imported by bare name via sys.path manipulation
LOCAL_MODULES = {"chat_template", "artifact_manifest", "split", "_lib"}
TRAINING_ENTRYPOINTS = ("train/sft.py", "train/merge.py")


def local_imports(source: Path) -> list[tuple[str, str]]:
    """(module, symbol) for every `from <local module> import <symbol>` at any nesting depth."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in LOCAL_MODULES:
            found.extend((node.module, alias.name) for alias in node.names)
    return found


@pytest.mark.parametrize("entrypoint", TRAINING_ENTRYPOINTS)
def test_late_bound_symbols_exist(entrypoint: str) -> None:
    imports = local_imports(ML_ROOT / entrypoint)
    assert imports, f"{entrypoint} imports nothing local — has the training path moved?"
    for module_name, symbol in imports:
        module = importlib.import_module(module_name)
        assert hasattr(module, symbol), (
            f"{entrypoint} does `from {module_name} import {symbol}`, but {module_name} has no "
            f"{symbol!r}. This import runs mid-run, so it would surface hours into training."
        )


def test_sft_writes_lineage_with_the_signature_write_lineage_accepts() -> None:
    """The lineage call is the last thing sft.py does; a signature drift loses the whole run."""
    import inspect

    from artifact_manifest import write_lineage

    tree = ast.parse((ML_ROOT / "train/sft.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "write_lineage"
    ]
    assert calls, "sft.py no longer records lineage — prime directive 4 requires it"

    params = inspect.signature(write_lineage).parameters
    for call in calls:
        for kw in call.keywords:
            assert kw.arg in params, f"write_lineage has no parameter {kw.arg!r}"
        required = {
            name
            for name, p in params.items()
            if p.default is inspect.Parameter.empty and p.kind is not p.VAR_KEYWORD
        }
        passed = {kw.arg for kw in call.keywords} | {"artifact_dir"}  # first arg is positional
        assert required <= passed, f"write_lineage missing required args: {required - passed}"


def test_formatting_func_matches_the_record_schema() -> None:
    """TRL feeds batches straight from the split shards, so the key names have to line up."""
    from chat_template import _Tokenizer, formatting_func

    class FakeTokenizer:
        # signature mirrors chat_template._Tokenizer exactly, parameter name included, so the
        # Protocol is satisfied structurally
        def apply_chat_template(self, conversation: Any, **kwargs: Any) -> str:
            return " | ".join(m["content"] for m in conversation)

    batch = {
        "messages": [
            [{"role": "user", "content": "س"}, {"role": "assistant", "content": "ج"}],
            [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}],
        ]
    }
    tokenizer: _Tokenizer = FakeTokenizer()
    rendered = formatting_func(tokenizer)(batch)
    assert rendered == ["س | ج", "q | a"]
