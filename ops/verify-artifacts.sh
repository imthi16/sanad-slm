#!/usr/bin/env bash
# Verify signatures before trusting an artifact (§10, §13 P6).
#
# CI signs images and model manifests with keyless cosign. Signing alone proves nothing to whoever
# pulls them — verification is the half that makes the signature mean something, and it was the
# half missing. This is what a sovereign operator runs before admitting an image to the cluster,
# and what the release checklist runs before publishing.
#
# Keyless verification checks *who* signed and *from where*, so both must be pinned: a signature
# from an unexpected identity is exactly the supply-chain substitution the signing was meant to
# stop. Defaults target this repo's GitHub Actions OIDC identity.
#
# Usage:
#   ops/verify-artifacts.sh image <ref>          # e.g. harbor.example/sanad/sanad-api:<sha>
#   ops/verify-artifacts.sh manifest <path>      # a model manifest.json + its .sig
#
# Env:
#   SANAD_CERT_IDENTITY_RE  override the expected signer identity regexp
#   SANAD_CERT_OIDC_ISSUER  override the expected OIDC issuer
set -euo pipefail

IDENTITY_RE="${SANAD_CERT_IDENTITY_RE:-^https://github.com/imthi16/sanad-slm/.github/workflows/.+@refs/heads/main$}"
OIDC_ISSUER="${SANAD_CERT_OIDC_ISSUER:-https://token.actions.githubusercontent.com}"

die() { echo "✗ $*" >&2; exit 1; }

command -v cosign >/dev/null || die "cosign not installed — https://docs.sigstore.dev/cosign/installation/"

mode="${1:-}"
target="${2:-}"
[[ -n "$mode" && -n "$target" ]] || die "usage: $0 {image|manifest} <ref-or-path>"

case "$mode" in
image)
    echo "→ verifying image signature: $target"
    echo "  expected signer: $IDENTITY_RE"
    cosign verify \
        --certificate-identity-regexp "$IDENTITY_RE" \
        --certificate-oidc-issuer "$OIDC_ISSUER" \
        "$target" >/dev/null || die "signature verification FAILED for $target — do not deploy it"
    echo "✓ image signature valid, signer matches"

    # A valid signature says who built it, not that it is safe. §10 wants both.
    if command -v trivy >/dev/null; then
        echo "→ re-scanning for HIGH/CRITICAL with a fix available"
        trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "$target" \
            || die "fixable HIGH/CRITICAL vulnerabilities present in $target"
        echo "✓ no fixable HIGH/CRITICAL findings"
    else
        echo "! trivy not installed — signature checked, vulnerabilities not re-verified"
    fi
    ;;
manifest)
    [[ -f "$target" ]] || die "manifest not found: $target"
    sig="${target}.sig"
    [[ -f "$sig" ]] || die "no signature beside the manifest: $sig"
    echo "→ verifying model manifest: $target"
    cosign verify-blob \
        --certificate-identity-regexp "$IDENTITY_RE" \
        --certificate-oidc-issuer "$OIDC_ISSUER" \
        --signature "$sig" \
        --certificate "${target}.pem" \
        "$target" >/dev/null || die "manifest signature verification FAILED — lineage is untrusted"
    echo "✓ manifest signature valid"

    # The manifest is the lineage record; an unsigned-but-valid-looking one is the thing to catch.
    for key in base_model base_revision data_manifest_sha256 train_config_sha256; do
        grep -q "\"$key\"" "$target" || die "manifest is missing $key — lineage incomplete (§5.5)"
    done
    echo "✓ lineage fields present: base → revision → data sha → config sha"
    ;;
*)
    die "unknown mode '$mode' — expected 'image' or 'manifest'"
    ;;
esac
