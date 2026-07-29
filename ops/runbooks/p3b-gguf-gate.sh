#!/usr/bin/env bash
# Re-run the GGUF gate with matched methodology (f16 GGUF baseline), then bench-edge.
# Entirely CPU: llama-perplexity on both sides. The GPU is not touched.
set -uo pipefail
LOG="$HOME/sanad-p3b.log"
exec >>"$LOG" 2>&1

LOCKDIR="$HOME/.sanad-p23.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "!!! another run holds $LOCKDIR — refusing $(date -Is)"; exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

echo; echo "===== p3b-rerun started $(date -Is) ====="
export PATH="$HOME/.local/bin:$PATH"
export HF_HOME="$HOME/sanad-hf"
# Belt and braces: nothing here needs CUDA, and the team has the card.
export CUDA_VISIBLE_DEVICES=""

die()   { echo "!!! ABORT: $*"; echo "===== p3b-rerun aborted $(date -Is) ====="; exit 1; }
stage() { echo; echo "########## $* — $(date -Is) ##########"; }

cd "$HOME/sanad-slm" || die "repo missing"

stage "preconditions"
[ -f ml/out/sanad-Q4_K_M.gguf ] || die "Q4_K_M missing"
[ -f ml/out/sanad-f16.gguf ]    || die "f16 GGUF baseline missing — needed for a like-for-like gate"
ls -la ml/out/sanad-f16.gguf ml/out/sanad-Q4_K_M.gguf

stage "pull"
git fetch --quiet origin && git pull -q && git log --oneline -1

stage "P3: ppl-gate (GGUF vs f16 GGUF, both via llama-perplexity, ΔPPL ≤ 5%)"
just ppl-gate out/sanad-Q4_K_M.gguf 2>&1 | tail -30 || die "GGUF PPL GATE RED"

stage "P3: edge bench (CPU only)"
just bench-edge 2>&1 | tail -30 || echo "!! bench-edge failed — the gate result above still stands"

stage "artifacts"
du -sh ml/out/* 2>/dev/null
ls -la ml/evals/reports/
cat ml/evals/reports/ppl_gate_sanad-Q4_K_M.gguf.json 2>/dev/null
df -h / | tail -1

echo "===== p3b-rerun done $(date -Is) ====="
