#!/usr/bin/env bash
# lm-evaluation-harness at a PINNED rev (§5.4a). Bump LM_EVAL_REV only via PR + rerun of ALL
# models in the comparator matrix — cross-rev numbers are never comparable.
#
# Usage: bash evals/harness/run_lm_eval.sh <model_path_or_hf_id> [run_id]
set -euo pipefail

# ── pins ────────────────────────────────────────────────────────────────────
LM_EVAL_REV="${LM_EVAL_REV:-6d642546f4688648fced259eb3302efd36ece5af}" # v0.4.12 · verified 2026-07-25
TASKS="arabicmmlu,aratrust,madinahqa,alrage"
NUM_FEWSHOT=0
# ────────────────────────────────────────────────────────────────────────────

MODEL="${1:?usage: run_lm_eval.sh <model> [run_id]}"
RUN_ID="${2:-$(date -u +%Y%m%dT%H%M%SZ)}"
ML_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ML_ROOT/evals/reports/$RUN_ID/$(basename "$MODEL")"

if [[ "$LM_EVAL_REV" == *"<"* ]]; then
    echo "✗ LM_EVAL_REV is unpinned — set the exact EleutherAI/lm-evaluation-harness commit" >&2
    exit 1
fi

# install the pinned harness into the ml venv (idempotent; offline mode uses the uv cache)
uv pip install "lm_eval[vllm] @ git+https://github.com/EleutherAI/lm-evaluation-harness@${LM_EVAL_REV}"

mkdir -p "$OUT"
uv run lm_eval --model vllm \
    --model_args "pretrained=${MODEL},dtype=bfloat16,gpu_memory_utilization=0.85" \
    --tasks "$TASKS" \
    --num_fewshot "$NUM_FEWSHOT" \
    --batch_size auto \
    --log_samples \
    --seed 3407 \
    --output_path "$OUT"

# stamp provenance into the report dir (prime directive 4)
{
    echo "model: $MODEL"
    echo "lm_eval_rev: $LM_EVAL_REV"
    echo "tasks: $TASKS"
    echo "num_fewshot: $NUM_FEWSHOT"
    echo "data_manifest_sha256: $(sha256sum "$ML_ROOT/data/MANIFEST.yaml" | cut -d' ' -f1)"
} > "$OUT/PROVENANCE.yaml"

echo "✓ report: $OUT (identical command must run for every model in the §5.2 matrix)"
