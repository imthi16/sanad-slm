#!/usr/bin/env bash
# `just helm-deploy <env>` — sops-decrypted values → helm upgrade --install of all charts (§12).
set -euo pipefail

ENV="${1:?usage: deploy.sh <dev|prod>}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHARTS="$DIR/charts"
SECRETS="$DIR/../../secrets/$ENV.sops.yaml"
NS=sanad

command -v sops >/dev/null || { echo "sops not installed" >&2; exit 1; }
[[ -f "$SECRETS" ]] || { echo "missing $SECRETS — create + encrypt it first (secrets/README.md)" >&2; exit 1; }

kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create ns "$NS"

# secrets land as one generic Secret per consumer, decrypted only in-memory
sops --decrypt "$SECRETS" | kubectl -n "$NS" apply -f -

MODE=$([[ "$ENV" == "prod" ]] && echo sovereign || echo dev)

helm upgrade --install sovereign-guard "$CHARTS/sovereign-guard" -n "$NS"
helm upgrade --install vllm "$CHARTS/vllm" -n "$NS"
helm upgrade --install sanad-api "$CHARTS/sanad-api" -n "$NS" --set mode="$MODE"
helm upgrade --install sanad-web "$CHARTS/sanad-web" -n "$NS"

echo "✓ deployed to $NS (mode=$MODE). eval runs: helm install eval-<id> $CHARTS/eval-job --set runId=<id>"
