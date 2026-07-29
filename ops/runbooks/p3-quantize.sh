#!/usr/bin/env bash
# P3 only: AWQ → ppl-gate → GGUF+imatrix → ppl-gate → bench-edge.
# Deliberately does NOT retrain. P2 finished at 10:29 on 2026-07-28 and out/merged-bf16 is the
# input here; re-running the full chain would spend 45 GPU-minutes reproducing what already exists.
set -uo pipefail
LOG="$HOME/sanad-p3.log"
exec >>"$LOG" 2>&1

LOCKDIR="$HOME/.sanad-p23.lock"   # shared with the full chain: never both at once
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "!!! another run holds $LOCKDIR — refusing $(date -Is)"
  exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

echo "===== p3 started $(date -Is) ====="

export PATH="$HOME/.local/bin:$PATH"
export HF_HOME="$HOME/sanad-hf"
[ -f "$HOME/.cache/huggingface/token" ] && export HF_TOKEN="$(cat "$HOME/.cache/huggingface/token")"

die()   { echo "!!! ABORT: $*"; echo "===== p3 aborted $(date -Is) ====="; exit 1; }
stage() { echo; echo "########## $* — $(date -Is) ##########"; }

cd "$HOME/sanad-slm" || die "repo missing"

stage "preconditions"
# The whole point of this script is that P2's output already exists. Prove it rather than
# discovering a missing input three stages in.
[ -f ml/out/merged-bf16/model.safetensors.index.json ] || die "out/merged-bf16 missing — run the full chain"
[ -f ml/data/processed/calib_bilingual_512.jsonl ]     || die "AWQ calibration set missing — run `just data`"
[ -f ml/data/processed/calib_bilingual.txt ]           || die "imatrix calibration text missing"
[ -f ml/data/processed/ppl_heldout_bilingual.jsonl ]   || die "ppl holdout missing"
du -sh ml/out/merged-bf16
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
df -h / | tail -1

stage "free the GPU"
ollama stop qwen2.5:32b 2>/dev/null || true
for _ in $(seq 1 30); do
  USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  [ "$USED" -lt 2000 ] && break
  sleep 5
done

stage "pull"
git fetch --quiet origin || die "git fetch failed"
git pull -q || die "git pull failed — resolve by hand"
git log --oneline -1

stage "P3: AWQ W4A16 (offload_device=cpu — see recipe)"
just quant-awq 2>&1 | tail -40 || die "AWQ quantization failed"
du -sh ml/out/awq-w4a16 2>/dev/null

stage "P3: ppl-gate (AWQ, ΔPPL ≤ 3%)"
just ppl-gate out/awq-w4a16 2>&1 | tail -25 || die "AWQ PPL GATE RED — not releasable"

stage "P3: GGUF Q4_K_M + bilingual imatrix"
# No nvcc here, so gguf.sh autodetects and builds CPU-only; the imatrix pass and the GGUF
# perplexity gate below are the slowest steps of this script by a wide margin.
just quant-gguf 2>&1 | tail -50 || die "GGUF export failed"

stage "P3: ppl-gate (GGUF, ΔPPL ≤ 5%)"
just ppl-gate out/sanad-Q4_K_M.gguf 2>&1 | tail -25 || die "GGUF PPL GATE RED — not releasable"

stage "P3: edge bench"
# RAPL is unreadable without sudo on this box, so watts stay blank; tok/s is the number that
# matters and it is labeled platform: x86-local.
just bench-edge 2>&1 | tail -25 || echo "!! bench-edge failed — artifacts above are still valid"

stage "artifacts"
ls -la ml/out/ 2>/dev/null
du -sh ml/out/* 2>/dev/null
ls -la ml/evals/reports/ 2>/dev/null
df -h / | tail -1

echo "===== p3 done $(date -Is) ====="
