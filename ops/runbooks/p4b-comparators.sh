#!/usr/bin/env bash
# P4b — close the quantization gate's ArabicMMLU clause, settle the <tool_call> root cause, and
# fill the comparator column. Ordered cheapest-and-most-certain first, so a late failure still
# leaves the earlier evidence on disk.
#
# Footprint discipline (shared box, 94% full): comparators are pulled ONE AT A TIME and deleted
# immediately after their eval. Never both resident. Downloads go to HF_HOME=$HOME/sanad-hf so the
# whole footprint is removable without touching the shared ~/.cache/huggingface cache.
set -uo pipefail
LOG="$HOME/sanad-p4b.log"
exec >>"$LOG" 2>&1

LOCKDIR="$HOME/.sanad-p4b.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "!!! another P4b run holds $LOCKDIR — refusing $(date -Is)"; exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

echo; echo "===== p4b started $(date -Is) ====="
export PATH="$HOME/.local/bin:$PATH"
export HF_HOME="$HOME/sanad-hf"
# HF_HOME relocates the token lookup to $HF_HOME/token, which does not exist — so a gated repo
# (jais is gated:auto) would 401 despite the account having accepted the terms. Read the real token.
[ -f "$HOME/.cache/huggingface/token" ] && export HF_TOKEN="$(cat "$HOME/.cache/huggingface/token")"

REPO="$HOME/sanad-slm"
BRANCH="feat/p1-synthetic-bank-drafts"
MIN_GB=40

die()   { echo "!!! ABORT: $*"; echo "===== p4b aborted $(date -Is) ====="; exit 1; }
stage() { echo; echo "########## $* — $(date -Is) ##########"; }
freegb(){ df --output=avail -BG / | tail -1 | tr -dc '0-9'; }

stage "preconditions"
df -h / | tail -1
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
[ "$(freegb)" -ge "$MIN_GB" ] || die "only $(freegb) GB free — need ${MIN_GB} GB headroom for a 7B pull"
cd "$REPO" || die "repo missing"
git fetch --quiet origin && git checkout -q "$BRANCH" && git pull -q
git log --oneline -1
[ -f ml/out/awq-w4a16/model.safetensors ] || die "awq-w4a16 not uploaded"

# Full output per model; only a summary reaches this log. Piping a GPU run through `tail` is what
# hid two root causes on 2026-07-28/29.
run_eval() {  # run_eval <model> <run_id> <label> [extra_model_args]
  local model="$1" run_id="$2" label="$3" extra="${4:-}"
  local elog="$HOME/sanad-p4b-${run_id}.log"
  # Idempotent: a completed report is expensive GPU time, never redone on a re-run of the chain.
  if find "ml/evals/reports/$run_id" -name 'results*.json' 2>/dev/null | grep -q .; then
    echo "⏭  $label already has a report — skipping (delete ml/evals/reports/$run_id to force)"
    return
  fi
  if SANAD_LM_EVAL_EXTRA_ARGS="$extra" bash ml/evals/harness/run_lm_eval.sh "$model" "$run_id" >"$elog" 2>&1; then
    echo "✓ $label eval OK — $elog"
    grep -E '^\|\s*(arabicmmlu|-)' "$elog" | tail -8
  else
    echo "!! $label eval FAILED (exit $?) — $elog"
    grep -nE "ValueError|RuntimeError|OSError|KeyError|are not supported|not a supported|401|403|GatedRepo|Tasks not found|out of memory" "$elog" \
      | grep -vE "raise |^\s*[0-9]+:\s*File " | head -10
    tail -20 "$elog"
  fi
}

# ── 1. AWQ: the §5.3 "ArabicMMLU drop > 1.0 pt" clause, never exercised ──────
stage "P4b-1: lm-eval — AWQ W4A16 (ml/out/awq-w4a16)"
run_eval ml/out/awq-w4a16 awq "AWQ"

# ── 2. <tool_call> root cause: same weights, AWQ instead of GGUF ─────────────
stage "P4b-2: <tool_call> isolation through vLLM + AWQ"
# This calls the venv python DIRECTLY rather than through run_lm_eval.sh, so it does not inherit the
# harness's PATH fix — and hit the identical `FileNotFoundError: 'ninja'` on the first attempt.
# Same bug, second call site: absolute-path invocation is not activation.
export PATH="$REPO/ml/.venv-eval/bin:$PATH"
# vLLM releases VRAM asynchronously on teardown; this starts ~2 s after the eval's engine exits, so
# give the card a moment rather than racing it.
sleep 30
nvidia-smi --query-gpu=memory.used --format=csv,noheader
"$REPO/ml/.venv-eval/bin/python" - <<'PY' > "$HOME/sanad-p4b-toolcall.log" 2>&1
import json
from vllm import LLM, SamplingParams
from transformers import AutoTokenizer

M = "ml/out/awq-w4a16"
llm = LLM(model=M, dtype="bfloat16", gpu_memory_utilization=0.85, max_model_len=8192)
tok = AutoTokenizer.from_pretrained(M)
sp = SamplingParams(temperature=0.0, max_tokens=120, seed=3407)
q = "ما هي أنواع الحسابات المصرفية المتاحة؟"

out = {}
# (a) raw text, no chat template — the case that was CLEAN on the GGUF
out["raw_no_template"] = llm.generate([q], sp)[0].outputs[0].text
# (b) chat template applied, enable_thinking=False — the case that LEAKED on the GGUF
templated = tok.apply_chat_template(
    [{"role": "user", "content": q}], tokenize=False,
    add_generation_prompt=True, enable_thinking=False,
)
out["chat_template"] = llm.generate([templated], sp)[0].outputs[0].text
out["templated_prompt_tail"] = templated[-220:]
out["has_tool_call"] = {k: ("<tool_call>" in v) for k, v in out.items() if isinstance(v, str)}
# token ids for the think/tool_call specials — the suspected GGUF mismapping
out["special_ids"] = {
    t: tok.convert_tokens_to_ids(t)
    for t in ("<think>", "</think>", "<tool_call>", "</tool_call>")
}
print(json.dumps(out, ensure_ascii=False, indent=2))
PY
if [ $? -eq 0 ]; then
  echo "✓ toolcall isolation done"
  grep -A6 '"has_tool_call"' "$HOME/sanad-p4b-toolcall.log" | head -12
  grep -A6 '"special_ids"' "$HOME/sanad-p4b-toolcall.log" | head -8
  cp "$HOME/sanad-p4b-toolcall.log" "$REPO/ml/evals/reports/toolcall_awq_vllm.json" 2>/dev/null
else
  echo "!! toolcall isolation failed"; tail -15 "$HOME/sanad-p4b-toolcall.log"
fi

# ── 3+4. comparators, one at a time, deleted after ───────────────────────────
comparator() {  # comparator <hf_id> <run_id> <label> [extra]
  local id="$1" run_id="$2" label="$3" extra="${4:-}"
  local cache_dir="$HF_HOME/hub/models--${id//\//--}"
  stage "P4b: comparator — $label ($id)"
  echo "free before: $(freegb) GB"
  if [ "$(freegb)" -lt "$MIN_GB" ]; then
    echo "!! skipping $label — only $(freegb) GB free"; return
  fi
  run_eval "$id" "$run_id" "$label" "$extra"
  echo "--- removing $label weights (footprint discipline) ---"
  rm -rf "$cache_dir"
  echo "free after: $(freegb) GB"
}

# ALLaM caps at max_position_embeddings=4096; the harness now clamps to min(ceiling, model max), so
# no per-model override is needed here. Nothing is truncated either way — the longest ArabicMMLU
# 0-shot prompt measured 3,615 chars ≈ 1,205 tokens across all 14,455 items.
comparator humain-ai/ALLaM-7B-Instruct-preview comparator-allam "ALLaM-7B-Instruct-preview"

# jais is gated:auto and the box's HF account (JoyMerlin) is NOT on the authorised list — a human
# must click "Agree and access repository" once at the URL below while logged in as that account.
# Attempting it costs 15 s and a 403, so probe first and say so plainly instead of failing a stage.
stage "P4b: comparator — jais-family-6.7b-chat (gating probe)"
if "$REPO/ml/.venv-eval/bin/python" -c "
import os
from huggingface_hub import HfApi
api = HfApi(token=os.environ.get('HF_TOKEN'))
api.model_info('inceptionai/jais-family-6p7b-chat', files_metadata=False)
list(api.list_repo_files('inceptionai/jais-family-6p7b-chat'))[:1]
" >/dev/null 2>&1; then
  comparator inceptionai/jais-family-6p7b-chat comparator-jais "jais-family-6.7b-chat" "trust_remote_code=True"
else
  echo "!! SKIPPED — jais is gated and this HF account is not authorised."
  echo "   Accept once at https://huggingface.co/inceptionai/jais-family-6p7b-chat (button:"
  echo "   'Agree and access repository'), logged in as the account owning ~/.cache/huggingface/token,"
  echo "   then re-run. This is a human click, not an automatable step."
fi

stage "reports"
find ml/evals/reports -name 'results*.json' -o -name 'PROVENANCE.yaml' | sort
df -h / | tail -1
du -sh "$HF_HOME" 2>/dev/null

stage "training venv integrity (ADR-0006)"
[ -x ml/.venv/bin/python ] && ml/.venv/bin/python -c "import torch;print('train venv torch:',torch.__version__)" 2>&1 \
  || echo "(training venv not restored — nothing to check)"

echo "===== p4b done $(date -Is) ====="
