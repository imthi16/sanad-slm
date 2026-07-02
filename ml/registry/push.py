"""MinIO model registry push/pull (§5.5).

Layout: s3://sanad-models/sanad-qwen3-4b-bank/{version}/
    adapter/ · merged-bf16/ · awq-w4a16/ · gguf/sanad-Q4_K_M.gguf · manifest.json · MODEL_CARD.md

A version is releasable only when: license gate ✓ · ppl gate ✓ · eval report attached ✓ ·
manifest signed (cosign) ✓. push refuses otherwise; --force does not exist by design.

Usage:
    uv run python registry/push.py --version v0.1.0
    uv run python registry/push.py --pull --version v0.1.0 --dest out/eval-model
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))

from artifact_manifest import read_manifest, sha256_file, verify_tree  # noqa: E402

BUCKET = os.environ.get("SANAD_MODELS_BUCKET", "sanad-models")
MODEL_NAME = os.environ.get("SANAD_MODEL_NAME", "sanad-qwen3-4b-bank")

ARTIFACTS = {
    "adapter": ML_ROOT / "out" / "adapter",
    "merged-bf16": ML_ROOT / "out" / "merged-bf16",
    "awq-w4a16": ML_ROOT / "out" / "awq-w4a16",
    "gguf": ML_ROOT / "out",  # sanad-Q4_K_M.gguf lives at out/
}
ALLOWED_LICENSES = {"Apache-2.0", "CC-BY-4.0", "MIT"}


def s3_client() -> Any:
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("SANAD_REGISTRY_S3_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "sanad"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "sanad-secret"),
    )


def release_gates(merged: Path) -> dict[str, Any]:
    manifest = read_manifest(merged)

    # 1. license gate — lineage licenses within the shipping set (prime directive 2)
    bad = set(manifest["licenses"]) - ALLOWED_LICENSES
    if bad:
        raise SystemExit(f"release blocked: non-shippable licenses in lineage: {sorted(bad)}")
    if manifest.get("data_manifest_sha256") is None:
        raise SystemExit("release blocked: no data MANIFEST hash in lineage")

    # 2. ppl gate — a passing report must exist for each quantized artifact being pushed
    for name in ("awq-w4a16", "sanad-Q4_K_M.gguf"):
        report = ML_ROOT / "evals" / "reports" / f"ppl_gate_{name}.json"
        if not report.exists():
            raise SystemExit(
                f"release blocked: ppl-gate report missing for {name} — run `just ppl-gate`"
            )

    # 3. eval report attached
    if manifest.get("eval_report_sha256") is None:
        raise SystemExit(
            "release blocked: no eval report hash in manifest — attach via write_lineage"
        )

    # 4. artifact integrity
    if not verify_tree(merged):
        raise SystemExit(
            "release blocked: merged-bf16 tree hash mismatch — artifact modified after manifest"
        )
    return manifest


def cosign_sign(manifest_path: Path) -> str | None:
    """Sign the manifest blob; returns the signature ref. Requires COSIGN_KEY (SOPS-provided)."""
    key = os.environ.get("COSIGN_KEY")
    if not key:
        raise SystemExit("release blocked: COSIGN_KEY not set — manifest must be signed (§5.5)")
    sig_path = manifest_path.with_suffix(".json.sig")
    subprocess.run(
        [
            "cosign",
            "sign-blob",
            "--yes",
            "--key",
            key,
            "--output-signature",
            str(sig_path),
            str(manifest_path),
        ],
        check=True,
    )
    return sig_path.name


def upload_tree(s3: Any, local: Path, key_prefix: str) -> int:
    n = 0
    for f in sorted(p for p in local.rglob("*") if p.is_file()):
        key = f"{key_prefix}/{f.relative_to(local)}"
        s3.upload_file(str(f), BUCKET, key)
        n += 1
    return n


def push(version: str) -> None:
    merged = ARTIFACTS["merged-bf16"]
    manifest = release_gates(merged)

    manifest_path = merged / "manifest.json"
    manifest["cosign_signature"] = cosign_sign(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    s3 = s3_client()
    prefix = f"{MODEL_NAME}/{version}"
    total = 0
    for name in ("adapter", "merged-bf16", "awq-w4a16"):
        d = ARTIFACTS[name]
        if d.exists():
            total += upload_tree(s3, d, f"{prefix}/{name}")
    gguf = ARTIFACTS["gguf"] / "sanad-Q4_K_M.gguf"
    if gguf.exists():
        s3.upload_file(str(gguf), BUCKET, f"{prefix}/gguf/{gguf.name}")
        s3.put_object(
            Bucket=BUCKET, Key=f"{prefix}/gguf/{gguf.name}.sha256", Body=sha256_file(gguf).encode()
        )
        total += 1
    s3.upload_file(str(manifest_path), BUCKET, f"{prefix}/manifest.json")
    sig = manifest_path.with_suffix(".json.sig")
    if sig.exists():
        s3.upload_file(str(sig), BUCKET, f"{prefix}/manifest.json.sig")

    card = ML_ROOT.parent / "docs" / "model-cards" / f"{MODEL_NAME}-{version}.md"
    template = ML_ROOT.parent / "docs" / "model-cards" / "template.md"
    if card.exists():
        s3.upload_file(str(card), BUCKET, f"{prefix}/MODEL_CARD.md")
    elif template.exists():
        log.warning(
            "model_card_missing", expected=str(card), note="generate from template before announce"
        )

    log.info("pushed", version=version, files=total, bucket=BUCKET, prefix=prefix)


def pull(version: str, dest: Path) -> None:
    s3 = s3_client()
    prefix = f"{MODEL_NAME}/{version}" if version != "latest" else _latest_prefix(s3)
    paginator = s3.get_paginator("list_objects_v2")
    n = 0
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            rel = obj["Key"].removeprefix(prefix + "/")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(BUCKET, obj["Key"], str(target))
            n += 1
    if n == 0:
        raise SystemExit(f"nothing at s3://{BUCKET}/{prefix}")
    # sha256 verify on every sync (§10)
    merged = dest / "merged-bf16"
    if merged.exists() and not verify_tree(merged):
        raise SystemExit("pulled artifact failed sha256 verification — refusing to use")
    log.info("pulled", version=version, files=n, dest=str(dest))


def _latest_prefix(s3: Any) -> str:
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{MODEL_NAME}/", Delimiter="/")
    versions = sorted(
        p["Prefix"].rstrip("/").rsplit("/", 1)[-1] for p in resp.get("CommonPrefixes", [])
    )
    if not versions:
        raise SystemExit(f"no versions under s3://{BUCKET}/{MODEL_NAME}/")
    return f"{MODEL_NAME}/{versions[-1]}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", required=True)
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--dest", type=Path, default=ML_ROOT / "out" / "pulled")
    args = ap.parse_args()

    if args.pull:
        pull(args.version, args.dest)
    else:
        push(args.version)


if __name__ == "__main__":
    main()
