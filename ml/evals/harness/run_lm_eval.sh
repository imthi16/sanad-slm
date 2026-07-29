#!/usr/bin/env bash
# lm-evaluation-harness at a PINNED rev (§5.4a). Bump LM_EVAL_REV only via PR + rerun of ALL
# models in the comparator matrix — cross-rev numbers are never comparable.
#
# Usage: bash evals/harness/run_lm_eval.sh <model_path_or_hf_id> [run_id]
set -euo pipefail

# ── pins ────────────────────────────────────────────────────────────────────
LM_EVAL_REV="${LM_EVAL_REV:-6d642546f4688648fced259eb3302efd36ece5af}" # v0.4.12 · verified 2026-07-25

# CLAUDE.md §15 lists ArabicMMLU / AraTrust / MadinahQA / ALRAGE as available "via lm-eval tasks".
# Only the first is true at this pinned commit: `aratrust`, `madinahqa` and `alrage` do not appear
# anywhere in the harness (grepped, not assumed), and there is no group named `alghafa` either —
# its subtasks are registered under other names. Asking for them cost a full P4 run on
# 2026-07-28, which died after building a 10 GB venv with "Tasks not found".
#
# arabicmmlu is a group of 45 subtasks (46 yaml files — one is the group itself) and is the
# benchmark §9.5's regression gate is defined on
# (fine-tuned within −1 pt of base = no catastrophic forgetting), so it is the one that matters.
# Adding the OALL-v2 leaderboard groups is a separate, much longer run — validate first.
TASKS="${SANAD_LM_EVAL_TASKS:-arabicmmlu}"
NUM_FEWSHOT=0

# Qwen3-4B-Instruct-2507 advertises max_position_embeddings=262144, and vLLM sizes its KV cache to
# the model's full context unless told otherwise: 36 GiB of KV against the 11.45 GiB left on a
# 24 GB card after weights, so the engine core refuses to start before a single token is scored.
# That killed both P4 evals on 2026-07-28 — identical `Engine core initialization failed` for
# fine-tuned and base, which reads like a broken environment and is really just a default.
# 8192 matches the serving envelope in CLAUDE.md §6.1 and is ~6.8× the longest ArabicMMLU 0-shot
# prompt (measured: 3,615 chars ≈ 1,205 tokens over all 14,455 items).
#
# It is a CEILING, not a fixed value: the effective length is min(this, the model's own
# max_position_embeddings), derived below. ALLaM-7B caps at 4096 and vLLM *refuses to start* when
# asked for more, so a single hard-pinned 8192 cannot evaluate the §5.2 comparator matrix at all.
# Clamping is safe for comparability here precisely because no prompt comes close to either bound —
# nothing is truncated at 4096 or at 8192, so the scores remain like-for-like. The check below
# enforces that reasoning rather than trusting it, and the effective value is stamped into
# PROVENANCE.yaml so a report always states what it actually ran with.
MAX_MODEL_LEN_CEILING="${SANAD_LM_EVAL_MAX_LEN:-8192}"
# Longest prompt the task set can produce, in tokens, with headroom. If the clamp ever lands below
# this, the run would silently truncate prompts and the scores would not be comparable — abort instead.
MIN_SAFE_MODEL_LEN="${SANAD_LM_EVAL_MIN_SAFE_LEN:-2048}"
GPU_MEM_UTIL="${SANAD_LM_EVAL_GPU_UTIL:-0.85}"

# Appended verbatim to --model_args, for per-model requirements that are NOT part of the
# measurement: `trust_remote_code=True` for comparators that ship custom modelling code
# (jais), for instance. Anything that changes *what is measured* belongs above as a pin, not
# here — the pins must stay identical across the §5.2 matrix, and this hook deliberately does not.
# Whatever is passed lands in PROVENANCE.yaml so a report always records it.
EXTRA_MODEL_ARGS="${SANAD_LM_EVAL_EXTRA_ARGS:-}"
# ────────────────────────────────────────────────────────────────────────────

MODEL="${1:?usage: run_lm_eval.sh <model> [run_id]}"
RUN_ID="${2:-$(date -u +%Y%m%dT%H%M%SZ)}"
ML_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ML_ROOT/evals/reports/$RUN_ID/$(basename "$MODEL")"

if [[ "$LM_EVAL_REV" == *"<"* ]]; then
    echo "✗ LM_EVAL_REV is unpinned — set the exact EleutherAI/lm-evaluation-harness commit" >&2
    exit 1
fi

# The harness goes in its OWN venv, never the training one. vLLM pins its own torch, and the
# training env is pinned to torch 2.10 with unsloth compiled against it (ADR-0006) — installing
# lm_eval[vllm] alongside it lets uv re-resolve torch and quietly destroy the environment that
# produced the model being evaluated. Separate venvs cost ~10 GB of disk and buy the guarantee
# that an eval can never invalidate a training run.
EVAL_VENV="${SANAD_EVAL_VENV:-$ML_ROOT/.venv-eval}"
if [[ ! -x "$EVAL_VENV/bin/lm_eval" ]]; then
    echo "→ creating isolated eval venv at $EVAL_VENV" >&2
    uv venv "$EVAL_VENV" --python 3.12
    # ninja is named explicitly because torch.compile shells out to it at RUNTIME. It currently
    # arrives as a transitive dep, so an upstream dropping it would surface as an inductor crash
    # 40 s into a GPU run rather than as a resolution error here.
    VIRTUAL_ENV="$EVAL_VENV" uv pip install ninja \
        "lm_eval[vllm] @ git+https://github.com/EleutherAI/lm-evaluation-harness@${LM_EVAL_REV}"
fi

# Put the venv's bin on PATH. Calling "$EVAL_VENV/bin/lm_eval" by absolute path runs the right
# interpreter but leaves $EVAL_VENV/bin *off* PATH — so vLLM's inductor backend, which shells out
# to `ninja` by bare name to build its kernels, died with
#   FileNotFoundError: [Errno 2] No such file or directory: 'ninja'
# while ninja sat installed in that very venv. Cost the second P4 attempt on 2026-07-29.
# Console-script build tools are only reachable through PATH; absolute-path invocation is not
# equivalent to activation.
export PATH="$EVAL_VENV/bin:$PATH"

# Sanity: the training venv must still hold the torch ADR-0006 pinned. If this ever fails, an
# eval has leaked into it and the training environment is no longer the one that trained.
if [[ -x "$ML_ROOT/.venv/bin/python" ]]; then
    TRAIN_TORCH=$("$ML_ROOT/.venv/bin/python" -c "import torch;print(torch.__version__)" 2>/dev/null || echo "absent")
    echo "→ training venv torch: $TRAIN_TORCH (must stay 2.10.x per ADR-0006)" >&2
fi

# Validate task names BEFORE loading a model. This is seconds of work and it is the check whose
# absence wasted the 2026-07-28 run: the task list was only resolved after vLLM had been installed,
# and a typo'd benchmark name is indistinguishable from a broken environment at that point.
echo "→ validating tasks: $TASKS" >&2
if ! "$EVAL_VENV/bin/lm_eval" validate --tasks "$TASKS" 2>&1 | tee /dev/stderr | grep -q "^Validating"; then
    echo "✗ could not validate tasks — is the harness installed?" >&2
    exit 1
fi
if "$EVAL_VENV/bin/lm_eval" validate --tasks "$TASKS" 2>&1 | grep -q "not found"; then
    echo "✗ unknown task name(s) in '$TASKS' — list them with: lm_eval ls tasks" >&2
    exit 1
fi

# Derive the effective context length: min(ceiling, model's own max_position_embeddings). Done here,
# before the GPU is touched, because vLLM's failure mode for asking too much is a pydantic
# ValidationError 20 s in rather than a clamp.
echo "→ deriving max_model_len (ceiling ${MAX_MODEL_LEN_CEILING})" >&2
MAX_MODEL_LEN=$("$EVAL_VENV/bin/python" - "$MODEL" "$MAX_MODEL_LEN_CEILING" <<'PY'
import sys
ceiling = int(sys.argv[2])
try:
    from transformers import AutoConfig
    cfg = AutoConfig.from_pretrained(sys.argv[1], trust_remote_code=True)
    mpe = getattr(cfg, "max_position_embeddings", None) or getattr(cfg, "n_positions", None)
    print(min(ceiling, int(mpe)) if mpe else ceiling)
except Exception as exc:  # noqa: BLE001 — any failure falls back to the ceiling, loudly
    print(f"could not read config ({type(exc).__name__}), using ceiling", file=sys.stderr)
    print(ceiling)
PY
)
if [[ ! "$MAX_MODEL_LEN" =~ ^[0-9]+$ ]]; then
    echo "✗ could not derive max_model_len (got '$MAX_MODEL_LEN')" >&2
    exit 1
fi
if (( MAX_MODEL_LEN < MIN_SAFE_MODEL_LEN )); then
    echo "✗ effective max_model_len ${MAX_MODEL_LEN} < ${MIN_SAFE_MODEL_LEN} — prompts would be" >&2
    echo "  truncated and the scores would not be comparable across the matrix. Refusing." >&2
    exit 1
fi
echo "→ max_model_len: ${MAX_MODEL_LEN} (ceiling ${MAX_MODEL_LEN_CEILING})" >&2

mkdir -p "$OUT"
MODEL_ARGS="pretrained=${MODEL},dtype=bfloat16,gpu_memory_utilization=${GPU_MEM_UTIL},max_model_len=${MAX_MODEL_LEN}"
[[ -n "$EXTRA_MODEL_ARGS" ]] && MODEL_ARGS="${MODEL_ARGS},${EXTRA_MODEL_ARGS}"
echo "→ model_args: $MODEL_ARGS" >&2
"$EVAL_VENV/bin/lm_eval" --model vllm \
    --model_args "$MODEL_ARGS" \
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
    echo "max_model_len: $MAX_MODEL_LEN            # effective = min(ceiling, model max_position_embeddings)"
    echo "max_model_len_ceiling: $MAX_MODEL_LEN_CEILING"
    echo "gpu_memory_utilization: $GPU_MEM_UTIL"
    echo "extra_model_args: ${EXTRA_MODEL_ARGS:-none}"
    echo "seed: 3407"
    echo "eval_venv: $EVAL_VENV"
    echo "data_manifest_sha256: $(sha256sum "$ML_ROOT/data/MANIFEST.yaml" | cut -d' ' -f1)"
} > "$OUT/PROVENANCE.yaml"

echo "✓ report: $OUT (identical command must run for every model in the §5.2 matrix)"
