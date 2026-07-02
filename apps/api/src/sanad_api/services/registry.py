"""Registry service — reads model manifests directly from MinIO (§5.5, /v1/registry)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from sanad_api.core.config import Settings

log = structlog.get_logger()


def _client(settings: Settings) -> Any:
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.registry_s3_endpoint,
        aws_access_key_id=settings.registry_access_key,
        aws_secret_access_key=settings.registry_secret_key,
    )


def _list_artifacts_sync(settings: Settings) -> list[dict[str, Any]]:
    s3 = _client(settings)
    bucket = settings.registry_bucket
    artifacts: list[dict[str, Any]] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Delimiter="/"):
        for model_prefix in page.get("CommonPrefixes", []):
            model_name = model_prefix["Prefix"].rstrip("/")
            versions = s3.list_objects_v2(
                Bucket=bucket, Prefix=model_prefix["Prefix"], Delimiter="/"
            )
            for vp in versions.get("CommonPrefixes", []):
                version = vp["Prefix"].rstrip("/").rsplit("/", 1)[-1]
                manifest_key = f"{vp['Prefix']}manifest.json"
                try:
                    body = s3.get_object(Bucket=bucket, Key=manifest_key)["Body"].read()
                    manifest = json.loads(body)
                except Exception:
                    manifest = None
                sig_exists = False
                try:
                    s3.head_object(Bucket=bucket, Key=f"{vp['Prefix']}manifest.json.sig")
                    sig_exists = True
                except Exception:
                    pass
                artifacts.append(
                    {
                        "model_name": model_name,
                        "version": version,
                        "manifest": manifest,
                        "sha256": manifest.get("artifact_sha256") if manifest else None,
                        "cosign_signed": sig_exists,
                        "licenses": manifest.get("licenses", []) if manifest else [],
                    }
                )
    return artifacts


async def list_artifacts(settings: Settings) -> list[dict[str, Any]]:
    try:
        return await asyncio.to_thread(_list_artifacts_sync, settings)
    except Exception as exc:
        log.warning("registry_unavailable", reason=str(exc))
        return []


def lineage_graph(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    """base → data → config → eval hash chain per version, for the Registry page."""
    nodes, edges = [], []
    for a in artifacts:
        m = a.get("manifest") or {}
        vid = f"{a['model_name']}@{a['version']}"
        nodes.append({"id": vid, "kind": "artifact", "cosign_signed": a["cosign_signed"]})
        if m.get("base_model"):
            base = f"{m['base_model']}@{m.get('base_revision', '?')[:8]}"
            nodes.append({"id": base, "kind": "base"})
            edges.append({"from": base, "to": vid, "label": "fine-tuned"})
        if m.get("data_manifest_sha256"):
            data_node = f"data@{m['data_manifest_sha256'][:8]}"
            nodes.append({"id": data_node, "kind": "data"})
            edges.append({"from": data_node, "to": vid, "label": "trained-on"})
        if m.get("eval_report_sha256"):
            eval_node = f"eval@{m['eval_report_sha256'][:8]}"
            nodes.append({"id": eval_node, "kind": "eval"})
            edges.append({"from": vid, "to": eval_node, "label": "evaluated-by"})
    unique_nodes = list({n["id"]: n for n in nodes}.values())
    return {"nodes": unique_nodes, "edges": edges}
