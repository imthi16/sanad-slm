#!/usr/bin/env python3
"""Execute the §10 sovereignty checklist (`just sovereign-audit`).

§10 has been a markdown checkbox list since P0: nothing verified it, so "audited per release" meant
"someone read it". This turns the checks that need no running cluster into pass/fail, and — just as
importantly — names the ones that *do* need a cluster instead of quietly counting them as green.

Prime directive 1 is a build-mode claim. A claim nothing tests is a slogan, which is the exact
thing §0 says sovereignty must not be.

Stdlib only, so it runs from a bare checkout with no workspace synced.

Usage: python3 ops/sovereign_audit.py [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PASS, FAIL, WARN, MANUAL = "pass", "fail", "warn", "manual"


@dataclass
class Audit:
    rows: list[tuple[str, str, str, str]] = field(default_factory=list)

    def add(self, status: str, item: str, detail: str, remedy: str = "") -> None:
        self.rows.append((status, item, detail, remedy))

    def check(self, ok: bool, item: str, ok_detail: str, bad_detail: str, remedy: str = "") -> None:
        self.add(PASS if ok else FAIL, item, ok_detail if ok else bad_detail, "" if ok else remedy)

    @property
    def failed(self) -> int:
        return sum(1 for s, *_ in self.rows if s == FAIL)


def read(rel: str) -> str:
    path = REPO / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ── checks ────────────────────────────────────────────────────────────────────────────────────


def check_web_csp(a: Audit) -> None:
    conf = read("apps/web/nginx.conf")
    csp = re.search(r"Content-Security-Policy\s+\"([^\"]+)\"", conf)
    if not csp:
        a.add(FAIL, "web CSP", "no Content-Security-Policy header in nginx.conf", "add one")
        return
    policy = csp.group(1)
    a.check(
        "default-src 'self'" in policy,
        "web CSP",
        "default-src 'self'",
        f"default-src is not 'self': {policy[:60]}",
        "nginx.conf must serve default-src 'self'",
    )
    # a CSP that allows an external origin would undo verify-no-cdn at runtime
    external = re.findall(r"https?://[^\s;\"]+", policy)
    a.check(
        not external,
        "CSP has no external origins",
        "none",
        f"CSP permits {external}",
        "remove the external origin — sovereign mode serves everything same-origin",
    )
    a.check(
        "'unsafe-eval'" not in policy,
        "CSP forbids unsafe-eval",
        "absent",
        "'unsafe-eval' present",
        "drop unsafe-eval",
    )


def check_no_cdn_in_sources(a: Audit) -> None:
    """The built bundle is checked by verify-no-cdn; this catches a CDN font at the source."""
    css = read("apps/web/src/styles/global.css") + read("apps/web/src/styles/tokens.css")
    hits = [u for u in re.findall(r"https?://[^\s;\")]+", css) if "schema" not in u]
    a.check(
        not hits,
        "stylesheets self-hosted",
        "no remote url() or @import",
        f"remote reference(s) in CSS: {hits}",
        "vendor the asset via @fontsource instead",
    )
    dist = REPO / "apps/web/dist"
    if dist.exists():
        a.add(PASS, "web dist present", "run `just verify-no-cdn` for the built-bundle gate")
    else:
        a.add(WARN, "web dist", "not built — `just verify-no-cdn` not exercised in this audit")


def check_offline_overlay(a: Audit) -> None:
    overlay = read("infra/compose/compose.sovereign.yml")
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "NO_PROXY"):
        a.check(
            var in overlay,
            f"offline env: {var}",
            "set in the sovereign overlay",
            "missing from compose.sovereign.yml",
            "sovereign/edge must export it (§4)",
        )
    a.check(
        re.search(r"internal:\s*true", overlay) is not None,
        "compose network internal",
        "internal: true — outbound routing impossible at the network layer",
        "no `internal: true` network found",
        "the demo must not be able to route out, not merely be asked not to",
    )


def check_network_policies(a: Audit) -> None:
    netpol = read("infra/helm/charts/sovereign-guard/templates/networkpolicies.yaml")
    a.check(
        "default-deny-egress" in netpol and re.search(r"egress:\s*\[\]", netpol) is not None,
        "k8s default-deny egress",
        "default-deny-egress policy with an empty egress list",
        "no default-deny egress policy found",
        "sovereign-guard must deny egress by default and allow additively",
    )
    a.check(
        "kube-dns" in netpol,
        "k8s DNS allowance",
        "DNS explicitly allowed",
        "no DNS allowance — pods will fail to resolve in-cluster names",
    )


def check_egress_alert(a: Audit) -> None:
    rule = read("infra/helm/charts/sovereign-guard/templates/prometheusrule.yaml")
    a.check(
        "SanadSovereignEgress" in rule,
        "egress-zero alert",
        "SanadSovereignEgress PrometheusRule present",
        "alert missing",
        "§9.3: this alert firing = broken promise, so it must exist to fire",
    )
    a.check(
        "SanadSovereignGuardAbsent" in rule,
        "guard-absent alert",
        "alerts if the NetworkPolicies themselves vanish",
        "no guard-absent alert — a deleted policy would be silent",
    )


def check_secrets(a: Audit) -> None:
    secrets_dir = REPO / "secrets"
    plaintext: list[str] = []
    encrypted = 0
    if secrets_dir.exists():
        for path in secrets_dir.rglob("*.y*ml"):
            body = path.read_text(encoding="utf-8", errors="replace")
            if path.name.endswith(".sops.yaml") and ("ENC[" in body or "sops:" in body):
                encrypted += 1
            else:
                plaintext.append(str(path.relative_to(REPO)))

    # The placeholder recipient only becomes a live problem once something is encrypted to it:
    # then the file is unreadable by anyone who holds a real key. With no secrets yet it is a
    # to-do, not a breach — graded accordingly so this audit can gate CI without going red on
    # something only the key holder can fix.
    placeholder = "age1qqqq" in read(".sops.yaml")
    if placeholder and encrypted:
        a.add(
            FAIL,
            "SOPS recipient",
            f"{encrypted} encrypted file(s) against a PLACEHOLDER recipient — nobody can decrypt",
            "re-encrypt with a real age recipient: sops updatekeys secrets/*.sops.yaml",
        )
    elif placeholder:
        a.add(
            WARN,
            "SOPS recipient",
            "placeholder age key — harmless while no secrets exist, blocking before the first one",
            "age-keygen -o ~/.config/sops/age/keys.txt, then paste the public key into .sops.yaml",
        )
    else:
        a.add(PASS, "SOPS recipient", "real recipient configured")

    a.check(
        not plaintext,
        "secrets encrypted",
        f"{encrypted} SOPS file(s), no plaintext" if encrypted else "no secret files yet",
        f"unencrypted secret file(s): {plaintext}",
        "encrypt with sops before committing (§10)",
    )


def check_judge_sovereignty(a: Audit) -> None:
    cfg = read("ml/configs/eval/judge_3c3h.yaml")
    a.check(
        "sovereign: false" in cfg and "sovereign: true" in cfg,
        "judge sovereignty flags",
        "judges carry an explicit sovereign flag, so API-judge scores can be excluded",
        "judges are not flagged sovereign true/false",
        "§5.4c: API-judge scores must be storable-but-excluded, which needs the flag",
    )
    api = read("apps/api/src/sanad_api/core/config.py")
    a.check(
        "allow_external_judges" in api and 'self.mode != "dev"' in api,
        "external judges forced off",
        "settings force allow_external_judges=False outside dev",
        "no validator forcing external judges off in sovereign/edge",
        "prime directive 1: zero-egress modes cannot call an external judge",
    )
    a.check(
        re.search(r"persist_chats:\s*bool\s*=\s*False", api) is not None,
        "chat content not persisted",
        "persist_chats defaults to False",
        "persist_chats does not default to False",
        "§7.3: only usage metadata is stored by default",
    )


def check_supply_chain(a: Audit) -> None:
    ci = read(".github/workflows/ci.yml")
    a.check("trivy-action" in ci, "image vulnerability scan", "Trivy in ci.yml", "no Trivy step")
    a.check("sbom-action" in ci, "SBOM generation", "Syft in ci.yml", "no SBOM step")
    a.check(
        "cosign" in ci or "cosign" in read(".github/workflows/release.yml"),
        "image signing",
        "cosign wired in CI",
        "no cosign step",
    )
    verify = read("ops/verify-artifacts.sh")
    a.check(
        "cosign verify" in verify,
        "signature verification path",
        "ops/verify-artifacts.sh verifies before trusting",
        "nothing verifies a signature — signing alone proves nothing to a consumer",
        "§13 P6 requires a cosign verify path",
    )


def check_pii_scrubbing(a: Audit) -> None:
    logging_py = read("apps/api/src/sanad_api/core/logging.py")
    a.check(
        "784-" in logging_py,
        "PII: Emirates ID",
        "Emirates ID pattern scrubbed",
        "no Emirates ID pattern",
        "§10 requires AR+EN PII patterns",
    )
    a.check(
        "AE" in logging_py and "IBAN" in logging_py.upper(),
        "PII: UAE IBAN",
        "IBAN pattern scrubbed",
        "no UAE IBAN pattern",
    )
    # Arabic-Indic digits must scrub too, or an Arabic-entered ID leaks
    a.check(
        "٠" in logging_py or "arab" in logging_py.lower(),
        "PII: Arabic-Indic digits",
        "Arabic digit range handled",
        "patterns look Latin-digit only — an ID typed as ٧٨٤ would pass through",
        "extend the regexes to Arabic-Indic digits (§10)",
    )
    a.check(
        (REPO / "apps/api/tests/test_logging_pii.py").exists(),
        "PII scrubbing tested",
        "test_logging_pii.py present",
        "no PII scrubbing test",
    )


def check_cluster_only_items(a: Audit) -> None:
    """Never let this audit imply §10 is green when its headline item needs a live cluster."""
    a.add(
        MANUAL,
        "egress-zero for 24 h",
        "requires a running sovereign namespace with Prometheus",
        "deploy sovereign-guard, then confirm SanadSovereignEgress stayed green 24 h before a demo",
    )
    a.add(
        MANUAL,
        "signature admission policy",
        "requires Harbor with a cosign policy configured",
        "enable the Harbor project policy that blocks unsigned images",
    )
    a.add(
        MANUAL,
        "model artifact sha256 on sync",
        "requires MinIO and a real artifact to mirror",
        "verify `mc mirror` + sha256 check on the first registry-push",
    )


CHECKS = (
    check_web_csp,
    check_no_cdn_in_sources,
    check_offline_overlay,
    check_network_policies,
    check_egress_alert,
    check_secrets,
    check_judge_sovereignty,
    check_supply_chain,
    check_pii_scrubbing,
    check_cluster_only_items,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    audit = Audit()
    for check in CHECKS:
        check(audit)

    if args.json:
        print(
            json.dumps(
                [
                    {"status": s, "item": i, "detail": d, "remedy": r}
                    for s, i, d, r in audit.rows
                ],
                indent=2,
            )
        )
    else:
        icon = {PASS: "✓", FAIL: "✗", WARN: "!", MANUAL: "·"}
        width = max(len(i) for _, i, _, _ in audit.rows)
        print("\n  sovereignty audit — CLAUDE.md §10\n")
        for status, item, detail, remedy in audit.rows:
            print(f"  {icon[status]} {item.ljust(width)}  {detail}")
            if remedy:
                print(f"  {' ' * (width + 3)}→ {remedy}")
        counts = {k: sum(1 for s, *_ in audit.rows if s == k) for k in (PASS, FAIL, WARN, MANUAL)}
        print(
            f"\n  {counts[PASS]} pass · {counts[FAIL]} fail · {counts[WARN]} warn · "
            f"{counts[MANUAL]} need a live cluster"
        )
        print(
            "\n  The last group is NOT verified here. §10 is not green until those are confirmed "
            "on a deployed namespace.\n"
        )

    sys.exit(1 if audit.failed else 0)


if __name__ == "__main__":
    main()
