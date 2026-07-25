"""The tokenizer roster is duplicated in three places and must not drift (§5.4d).

`evals/fertility/measure.py`, `evals/fertility/sync_tokenizers.py` and the API's
`services/fertility.py` each carry the alias → model map. The API keys directories by
`org__model`, the other two by `org/model`, so a rename in one is invisible to the others: the
symptom is a tokenizer that silently disappears from the fertility table rather than an error.

ALLaM already moved orgs once (ALLaM-AI → humain-ai), so this is a drift that has happened.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
API_FERTILITY = ML_ROOT.parent / "apps" / "api" / "src" / "sanad_api" / "services" / "fertility.py"


def _load(path: Path, name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def api_known_tokenizers() -> dict[str, str]:
    """Parse the API's map without importing it — apps/api is a separate uv workspace."""
    source = API_FERTILITY.read_text(encoding="utf-8")
    block = re.search(r"KNOWN_TOKENIZERS = \{(.*?)\}", source, re.S)
    assert block, "KNOWN_TOKENIZERS not found in the API's fertility service"
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block.group(1)))


def test_sync_and_measure_agree_on_the_roster() -> None:
    sync = _load(ML_ROOT / "evals/fertility/sync_tokenizers.py", "sync_tokenizers")
    measure = _load(ML_ROOT / "evals/fertility/measure.py", "measure")
    assert sync.TOKENIZERS == measure.TOKENIZERS  # type: ignore[attr-defined]


def test_api_agrees_with_ml_on_the_roster() -> None:
    sync = _load(ML_ROOT / "evals/fertility/sync_tokenizers.py", "sync_tokenizers")
    ml_map: dict[str, str] = sync.TOKENIZERS  # type: ignore[attr-defined]
    api_map = api_known_tokenizers()

    assert set(api_map) == set(ml_map), (
        f"alias sets differ — api {sorted(set(api_map) ^ set(ml_map))} is the symmetric difference"
    )
    for alias, model_id in ml_map.items():
        # the API stores the same id with / replaced by __, because it keys a directory name
        assert api_map[alias] == model_id.replace("/", "__"), (
            f"{alias}: API has {api_map[alias]!r}, ml has {model_id!r} — a tokenizer whose id "
            "drifts here vanishes from the fertility table without an error"
        )


def test_target_dir_matches_the_api_directory_layout() -> None:
    sync = _load(ML_ROOT / "evals/fertility/sync_tokenizers.py", "sync_tokenizers")
    api_map = api_known_tokenizers()
    for alias, model_id in sync.TOKENIZERS.items():  # type: ignore[attr-defined]
        written = sync.target_dir(Path("/models/tokenizers"), model_id)  # type: ignore[attr-defined]
        assert written.name == api_map[alias], (
            f"sync writes {written.name!r} but the API loads {api_map[alias]!r}"
        )


def test_gated_hints_cover_the_gated_models() -> None:
    """§15 records these as gated; the sync must say what to do rather than just fail."""
    sync = _load(ML_ROOT / "evals/fertility/sync_tokenizers.py", "sync_tokenizers")
    hints: dict[str, str] = sync.GATED_HINT  # type: ignore[attr-defined]
    for model_id in ("meta-llama/Llama-3.2-3B-Instruct", "inceptionai/jais-family-6p7b-chat"):
        assert model_id in hints
        assert "HF_TOKEN" in hints[model_id]


def test_snapshot_revision_extracts_the_sha() -> None:
    sync = _load(ML_ROOT / "evals/fertility/sync_tokenizers.py", "sync_tokenizers")
    sha = "cdbee75f17c01a7cc42f958dc650907174af0554"
    cached = f"/cache/models--Qwen--Qwen3/snapshots/{sha}/tokenizer.json"
    assert sync.snapshot_revision(cached) == sha  # type: ignore[attr-defined]
    # anything not in the hub's snapshot layout must not be reported as a revision
    assert sync.snapshot_revision("/tmp/tokenizer.json") == "unknown"  # type: ignore[attr-defined]


def test_manifest_shape_is_json_with_model_and_revision() -> None:
    """The manifest is what ties a published tokens/word figure to a tokenizer version."""
    manifest = ML_ROOT / "out" / "tokenizers" / "tokenizers.manifest.json"
    if not manifest.exists():
        return  # nothing synced on this machine — the sync script's own run covers the shape
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for alias, info in data.items():
        assert {"model_id", "revision"} <= set(info), f"{alias} missing keys: {info}"
