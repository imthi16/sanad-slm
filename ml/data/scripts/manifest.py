"""MANIFEST.yaml builder + CI license/provenance gate (§5.1, prime directive 2).

  build  — validate all processed shards against the record schema, then regenerate
           MANIFEST.yaml: per-source counts, licenses, provenance/lang splits, shard sha256.
  gate   — fail (exit 1) if, for the given profile, any record's license is outside the
           allowed set, or any source references data/quarantine/. Run in CI as `just data-gate`.

Usage:
    python data/scripts/manifest.py build
    python data/scripts/manifest.py gate --profile commercial
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections import Counter
from pathlib import Path
from typing import Any

import structlog
import yaml
from _lib import MANIFEST_PATH, ML_ROOT, mlflow_step, read_jsonl, sha256_file, validate_records

log = structlog.get_logger()

PROCESSED = ML_ROOT / "data" / "processed"
ALLOWED_COMMERCIAL = {"Apache-2.0", "CC-BY-4.0", "MIT"}


def load_manifest() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    return data


def collect() -> tuple[list[dict[str, Any]], list[Path]]:
    shards = sorted(PROCESSED.glob("*.jsonl"))
    records = [r for s in shards for r in read_jsonl(s)]
    return records, shards


def build() -> None:
    records, shards = collect()
    validate_records(records)

    manifest = load_manifest()
    by_source = Counter(r["source"]["name"] for r in records)
    for src in manifest["sources"]:
        src["count"] = by_source.get(src["name"], 0)

    n = len(records) or 1
    prov = Counter(r["provenance"] for r in records)
    lang = Counter(r["lang"] for r in records)
    manifest["totals"] = {
        "records": len(records),
        # the native/translated/synthetic split is a rigor signal printed into every eval report
        "provenance_split": {
            k: round(prov.get(k, 0) / n, 4) for k in ("native", "translated", "synthetic")
        },
        "lang_split": {k: round(lang.get(k, 0) / n, 4) for k in ("ar", "en", "mixed")},
    }
    manifest["shards"] = [
        {
            "path": str(s.relative_to(ML_ROOT)),
            "sha256": sha256_file(s),
            "records": sum(1 for _ in read_jsonl(s)),
        }
        for s in shards
    ]
    manifest["generated_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")

    MANIFEST_PATH.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    log.info("manifest_built", records=len(records), shards=len(shards))
    mlflow_step("manifest_build", records=len(records), **manifest["totals"]["provenance_split"])


def gate(profile: str) -> None:
    manifest = load_manifest()
    if manifest.get("profile") != profile:
        raise SystemExit(
            f"manifest profile is '{manifest.get('profile')}', gate ran for '{profile}'"
        )

    allowed = set(manifest.get("allowed_licenses", [])) or ALLOWED_COMMERCIAL
    violations: list[str] = []

    for src in manifest["sources"]:
        if profile == "commercial" and src["license"] not in allowed:
            violations.append(
                f"source '{src['name']}': license '{src['license']}' ∉ {sorted(allowed)}"
            )
        if "quarantine" in str(src.get("url", "")):
            violations.append(
                f"source '{src['name']}': references data/quarantine/ — research-only"
            )

    # belt & braces: re-check record-level licenses in the shards themselves
    records, _ = collect()
    for r in records:
        lic = r["source"]["license"]
        if profile == "commercial" and lic not in allowed:
            violations.append(f"record {r['id']}: license '{lic}' ∉ {sorted(allowed)}")
            if len(violations) > 20:
                violations.append("… (truncated)")
                break

    if violations:
        for v in violations:
            log.error("license_gate_violation", detail=v)
        raise SystemExit(
            f"data-gate FAILED for profile '{profile}' — {len(violations)} violation(s)"
        )
    log.info("data_gate_ok", profile=profile, records=len(records))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    g = sub.add_parser("gate")
    g.add_argument("--profile", default="commercial")
    args = ap.parse_args()

    if args.cmd == "build":
        build()
    else:
        gate(args.profile)


if __name__ == "__main__":
    main()
