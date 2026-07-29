#!/usr/bin/env bash
# P4 — standardized benchmarks on fine-tuned vs base, cheapest-first.
#
# The server was erased at 14:00 today, so this restores before it evaluates. Ordered so that a
# failure late in the run still leaves the earlier reports on disk: fine-tuned first (the model we
# care about), then base (needed for the regression gate). Comparators are deliberately NOT here —
# they are 27 GB of downloads and hours more GPU, and the owner freed the card once already.
set -uo pipefail
LOG="$HOME/sanad-p4.log"
exec >>"$LOG" 2>&1

LOCKDIR="$HOME/.sanad-p4.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "!!! another P4 run holds $LOCKDIR — refusing $(date -Is)"; exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

echo; echo "===== p4 started $(date -Is) ====="
export PATH="$HOME/.local/bin:$PATH"
export HF_HOME="$HOME/sanad-hf"

die()   { echo "!!! ABORT: $*"; echo "===== p4 aborted $(date -Is) ====="; exit 1; }
stage() { echo; echo "########## $* — $(date -Is) ##########"; }

REPO="$HOME/sanad-slm"
BRANCH="feat/p1-synthetic-bank-drafts"

stage "preconditions"
df -h / | tail -1
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
# lm-eval + vLLM + base weights + the merged model need real room on a 92%-full disk.
FREE_GB=$(df --output=avail -BG / | tail -1 | tr -dc '0-9')
[ "$FREE_GB" -ge 60 ] || die "only ${FREE_GB} GB free — P4 needs ~60 GB (vLLM env, base weights, reports)"

stage "restore repo"
if [ ! -d "$REPO/.git" ]; then
  git clone --quiet --branch "$BRANCH" https://github.com/imthi16/sanad-slm.git "$REPO" || die "clone failed"
fi
cd "$REPO" || die "repo missing"
git fetch --quiet origin && git checkout -q "$BRANCH" && git pull -q
git log --oneline -1

stage "restore data (needed for MANIFEST provenance stamp)"
[ -f ml/data/MANIFEST.yaml ] || die "MANIFEST.yaml missing from the checkout"
ls -la ml/data/processed/ 2>/dev/null | head -5 || echo "(processed shards absent — only needed for the PROVENANCE hash, which reads MANIFEST)"

stage "check the uploaded fine-tuned model"
# .sanad_p4_upload.py puts merged-bf16 here before this script runs.
[ -f ml/out/merged-bf16/model.safetensors.index.json ] || die "ml/out/merged-bf16 not uploaded yet"
du -sh ml/out/merged-bf16

# Keep the FULL output per model in its own file and only summarise into this log. The 2026-07-28
# run piped straight into `tail -40`, which kept the re-raise and discarded the ValueError that
# actually explained it — the log said "Engine core initialization failed. See root cause above"
# with the root cause cut off. Diagnosing it needed a fresh GPU repro the next morning.
run_eval() {  # run_eval <model> <run_id> <label>
  local model="$1" run_id="$2" label="$3" elog="$HOME/sanad-p4-${2}.log"
  if bash ml/evals/harness/run_lm_eval.sh "$model" "$run_id" >"$elog" 2>&1; then
    echo "✓ $label eval OK — full output: $elog"
    tail -15 "$elog"
  else
    echo "!! $label eval FAILED (exit $?) — full output: $elog"
    echo "--- first real error ---"
    grep -nE "ValueError|RuntimeError|OSError|AssertionError|Tasks not found|CUDA|out of memory" "$elog" \
      | grep -v "raise \|^\s*File " | head -12
    echo "--- last 25 lines ---"
    tail -25 "$elog"
  fi
}

stage "P4a: lm-eval — FINE-TUNED (ml/out/merged-bf16)"
run_eval ml/out/merged-bf16 finetuned "fine-tuned"

stage "P4b: lm-eval — BASE (Qwen/Qwen3-4B-Instruct-2507, pinned rev)"
run_eval Qwen/Qwen3-4B-Instruct-2507 base "base"

stage "reports"
find ml/evals/reports -name 'results*.json' -o -name 'PROVENANCE.yaml' | sort
du -sh ml/evals/reports/* 2>/dev/null
df -h / | tail -1

stage "training venv integrity (ADR-0006)"
# If vLLM leaked into the training env, torch will no longer be 2.10.x and any future retrain
# would not be the run we documented.
[ -x ml/.venv/bin/python ] && ml/.venv/bin/python -c "import torch;print('train venv torch:',torch.__version__)" 2>&1 || echo "(training venv not restored — nothing to check)"

echo "===== p4 done $(date -Is) ====="
