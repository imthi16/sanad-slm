"""Model artifact manifest.json — lineage: base → data hash → train config hash → eval report
hash (§5.5, prime directive 4). Written next to every merged/quantized artifact; read by
registry/push.py (release gates) and the API's /v1/registry.
"""

from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import json
from pathlib import Path
from typing import Any

ML_ROOT = Path(__file__).resolve().parents[1]
DATA_MANIFEST = ML_ROOT / "data" / "MANIFEST.yaml"

MANIFEST_NAME = "manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Path) -> str:
    """Deterministic hash over a directory: sorted relative paths + content hashes."""
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file() and p.name != MANIFEST_NAME):
        h.update(str(f.relative_to(root)).encode())
        h.update(sha256_file(f).encode())
    return h.hexdigest()


def write_lineage(
    artifact_dir: Path,
    *,
    base_model: str,
    base_revision: str,
    train_config: Path,
    mlflow_run_id: str | None,
    eval_report: Path | None = None,
    licenses: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    manifest = {
        "schema_version": 1,
        "base_model": base_model,
        "base_revision": base_revision,
        "data_manifest_sha256": sha256_file(DATA_MANIFEST) if DATA_MANIFEST.exists() else None,
        "train_config": str(train_config.name),
        "train_config_sha256": sha256_file(train_config),
        "eval_report_sha256": sha256_file(eval_report) if eval_report else None,
        "artifact_sha256": sha256_tree(artifact_dir),
        "licenses": licenses or ["Apache-2.0"],
        "mlflow_run_id": mlflow_run_id,
        "created_by": getpass.getuser(),
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "cosign_signature": None,  # set by push.py after signing
        **(extra or {}),
    }
    out = artifact_dir / MANIFEST_NAME
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def read_manifest(artifact_dir: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((artifact_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    return data


def verify_tree(artifact_dir: Path) -> bool:
    """Recompute the tree hash and compare — used on every sync (§10)."""
    manifest = read_manifest(artifact_dir)
    return bool(manifest["artifact_sha256"] == sha256_tree(artifact_dir))
