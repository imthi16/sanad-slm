#!/usr/bin/env bash
# vLLM entrypoint (§6.1) — values templated by Helm/compose via env.
# Quantization is auto-detected from the compressed-tensors checkpoint: do NOT pass legacy
# --quantization awq flags unless vLLM explicitly asks for them.
set -euo pipefail

MODEL_DIR="${SANAD_MODEL_DIR:-/models/sanad-qwen3-4b-bank/awq-w4a16}"
SERVED_NAME="${SANAD_SERVED_NAME:-sanad-bank-awq}"
MAX_LEN="${SANAD_MAX_MODEL_LEN:-8192}"
GPU_UTIL="${SANAD_GPU_MEM_UTIL:-0.90}"

# boot fails loudly if the model dir is missing — no silent hub fetch (§10 checklist)
if [[ ! -d "$MODEL_DIR" ]] || [[ -z "$(ls -A "$MODEL_DIR" 2>/dev/null)" ]]; then
    echo "FATAL: model dir '$MODEL_DIR' missing or empty — initContainer sync failed?" >&2
    exit 1
fi
if [[ -f "$MODEL_DIR/manifest.json" ]]; then
    echo "serving artifact lineage:" && grep -E '"(base_model|artifact_sha256)"' "$MODEL_DIR/manifest.json" || true
fi

exec vllm serve "$MODEL_DIR" \
    --served-model-name "$SERVED_NAME" \
    --max-model-len "$MAX_LEN" \
    --gpu-memory-utilization "$GPU_UTIL" \
    --enable-prefix-caching \
    --disable-log-requests \
    --host 0.0.0.0 --port 8000
