#!/usr/bin/env bash
# llama-server launcher (§6.2) — CPU/edge-box serving of the GGUF artifact.
# For a 4B Q4_K_M: ~2.5–3 GB weights + 0.5–1.5 GB KV. Benchmark on the actual
# host/llama.cpp pair and record it (ops/runbooks/edge-bench.md → `just bench-edge`).
set -euo pipefail

MODEL="${SANAD_GGUF_PATH:-/models/sanad-Q4_K_M.gguf}"
CTX="${SANAD_CTX:-4096}"
PARALLEL="${SANAD_PARALLEL:-2}"
PORT="${SANAD_PORT:-8080}"

if [[ ! -f "$MODEL" ]]; then
    echo "FATAL: GGUF missing at $MODEL — sync it from MinIO first (mc mirror)" >&2
    exit 1
fi
if [[ -f "$MODEL.sha256" ]]; then
    echo "$(cat "$MODEL.sha256")  $MODEL" | sha256sum -c - || {
        echo "FATAL: GGUF sha256 mismatch — refusing to serve a corrupted model (§10)" >&2
        exit 1
    }
fi

exec llama-server \
    -m "$MODEL" \
    -ngl 99 \
    -c "$CTX" \
    --parallel "$PARALLEL" \
    --host 0.0.0.0 --port "$PORT" \
    --metrics
