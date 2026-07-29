#!/usr/bin/env bash
# SANAD P2 (train + merge) → P3 (AWQ, GGUF, gates, edge bench). Unattended, resumes nothing:
# each stage gates the next, because falling through a red gate into a multi-hour stage produces
# artifacts nobody can quote. Upload to ~ on the train box and run detached.
set -uo pipefail
LOG="$HOME/sanad-p23.log"
exec >>"$LOG" 2>&1

# Single-run lock. Acquired before the EXIT trap is installed, so a second invocation bails out
# without deleting the first one's lock. mkdir is the atomic primitive here — `[ -e ]` then
# create would race exactly when it matters.
LOCKDIR="$HOME/.sanad-p23.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "!!! another p2+p3 run holds $LOCKDIR — refusing to start a second $(date -Is)"
  exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

echo "===== p2+p3 started $(date -Is) ====="

export PATH="$HOME/.local/bin:$PATH"
export HF_HOME="$HOME/sanad-hf"
[ -f "$HOME/.cache/huggingface/token" ] && export HF_TOKEN="$(cat "$HOME/.cache/huggingface/token")"

die()   { echo "!!! ABORT: $*"; echo "===== p2+p3 aborted $(date -Is) ====="; exit 1; }
stage() { echo; echo "########## $* — $(date -Is) ##########"; }

# The commit that makes this run possible at all: fix(ml): resolve the Unsloth/TRL conflict.
# Training against anything older reproduces the 2026-07-26 ImportError six hours from now.
PIN_FIX=5c482d2

cd "$HOME/sanad-slm" || die "repo missing"

stage "free the GPU"
# ollama holds qwen2.5:32b (19.8 GB) and will contend for the 4090 mid-run.
ollama stop qwen2.5:32b 2>/dev/null || true
for _ in $(seq 1 30); do
  USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  [ "$USED" -lt 2000 ] && break
  sleep 5
done
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader

stage "pull the pin fix (ADR-0006)"
# Verify the pull, don't assume it. ml/data/MANIFEST.yaml is modified on this box from the P1 run
# and ml/mlflow.db is untracked; no incoming commit touches either, so this fast-forwards — but
# prove it, because the whole run is worthless against the old pins.
git fetch --quiet origin || die "git fetch failed — no network?"
git pull -q || die "git pull failed — working tree conflicts with incoming commits; resolve by hand"
git merge-base --is-ancestor "$PIN_FIX" HEAD || die \
  "$PIN_FIX (the ADR-0006 pin fix) is not an ancestor of HEAD $(git rev-parse --short HEAD) — \
refusing to spend the night training against the broken pins"
git log --oneline -1

stage "sync train + quant extras"
# First sync on the new lock: torch 2.10 + transformers 4.57.6 replace what is cached, so
# expect a real download here even though ~/.cache/uv is warm.
(cd ml && uv sync --extra train --extra quant 2>&1 | tail -8) || die "extras sync failed"

stage "preflight (now imports the stack for real — ADR-0006)"
just preflight 2>&1 | tail -35 || die "PREFLIGHT RED — not burning GPU hours on a known-bad setup"

stage "P2: train"
just train 2>&1 | tail -80 || die "training failed"

stage "P2: merge"
just merge 2>&1 | tail -20 || die "merge failed"
du -sh ml/out/* 2>/dev/null; df -h / | tail -1

stage "P3: AWQ W4A16"
just quant-awq 2>&1 | tail -30 || die "AWQ quantization failed"

stage "P3: ppl-gate (AWQ, ΔPPL ≤ 3%)"
just ppl-gate out/awq-w4a16 2>&1 | tail -20 || die "AWQ PPL GATE RED — not releasable"

stage "P3: GGUF Q4_K_M + bilingual imatrix"
# No nvcc on this box: gguf.sh now autodetects and builds CPU-only. The imatrix pass and the
# GGUF perplexity gate are the slowest steps of the night as a result.
just quant-gguf 2>&1 | tail -40 || die "GGUF export failed"

stage "P3: ppl-gate (GGUF, ΔPPL ≤ 5%)"
just ppl-gate out/sanad-Q4_K_M.gguf 2>&1 | tail -20 || die "GGUF PPL GATE RED — not releasable"

stage "P3: edge bench"
# RAPL is unreadable without sudo on this box, so watts will be blank; tok/s is the number
# that matters and it is labeled platform: x86-local.
just bench-edge 2>&1 | tail -25 || echo "!! bench-edge failed — artifacts above are still valid"

stage "artifacts"
ls -la ml/out/ 2>/dev/null
du -sh ml/out/* 2>/dev/null
ls -la ml/evals/reports/ 2>/dev/null
df -h / | tail -1

echo "===== p2+p3 done $(date -Is) ====="
