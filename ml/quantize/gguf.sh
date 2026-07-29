#!/usr/bin/env bash
# GGUF Q4_K_M export with bilingual importance matrix (§5.3).
# Q4_K_M = community sweet spot; the imatrix MUST be computed on bilingual text —
# an English-only imatrix quietly wrecks Arabic.
#
# Usage: bash quantize/gguf.sh [merged_model_dir]
set -euo pipefail

ML_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${1:-$ML_ROOT/out/merged-bf16}"
CFG="$ML_ROOT/configs/quant/gguf-q4km.yaml"

# Pin llama.cpp — read the rev from the config; bump only via PR + ppl-gate rerun.
LLAMA_CPP_REV="$(grep -oP 'rev:\s*"\K[^"]+' "$CFG")"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$ML_ROOT/out/llama.cpp}"
CALIB_TXT="$ML_ROOT/$(grep -oP 'calib_text:\s*\K\S+' "$CFG")"
F16_OUT="$ML_ROOT/$(grep -oP 'f16:\s*\K\S+' "$CFG")"
IMATRIX_OUT="$ML_ROOT/$(grep -oP 'imatrix:\s*\K\S+' "$CFG" | tail -1)"
Q4_OUT="$ML_ROOT/$(grep -oP 'quantized:\s*\K\S+' "$CFG")"

if [[ "$LLAMA_CPP_REV" == *"pin-llamacpp"* ]]; then
    echo "✗ llama.cpp rev is unpinned in $CFG — pin the exact commit sha first" >&2
    exit 1
fi
[[ -f "$CALIB_TXT" ]] || { echo "✗ bilingual calibration text missing: $CALIB_TXT" >&2; exit 1; }

# 1. fetch + build pinned llama.cpp (idempotent; offline mode requires a pre-synced checkout)
if [[ ! -d "$LLAMA_CPP_DIR" ]]; then
    if [[ "${HF_HUB_OFFLINE:-0}" == "1" ]]; then
        echo "✗ offline mode and no llama.cpp checkout at $LLAMA_CPP_DIR" >&2
        exit 1
    fi
    git clone https://github.com/ggml-org/llama.cpp "$LLAMA_CPP_DIR"
fi
git -C "$LLAMA_CPP_DIR" checkout "$LLAMA_CPP_REV"

# CUDA is opt-in by capability, not by default. A GPU is not enough — building the CUDA backend
# needs nvcc, and the train box has the driver without the toolkit, so a hardcoded ON failed the
# cmake configure step. Override explicitly with GGML_CUDA=ON/OFF when you know better.
if [[ -z "${GGML_CUDA:-}" ]]; then
    if command -v nvcc >/dev/null 2>&1; then GGML_CUDA=ON; else GGML_CUDA=OFF; fi
fi
echo "→ building llama.cpp with GGML_CUDA=$GGML_CUDA$([[ $GGML_CUDA == OFF ]] && echo ' (no nvcc on PATH — CPU build; imatrix and ppl will be slow)')"
cmake -S "$LLAMA_CPP_DIR" -B "$LLAMA_CPP_DIR/build" -DGGML_CUDA="$GGML_CUDA"
# llama-perplexity belongs in this list even though this script never calls it: `just ppl-gate`
# looks for it in exactly this build tree, and it is the release-blocking gate for the artifact
# produced two lines below. Omitting it meant the 2026-07-28 run built a perfectly good
# Q4_K_M and then aborted with "GGUF PPL GATE RED" that was a missing binary, not a quality
# failure — the most expensive possible way to discover a one-word omission.
cmake --build "$LLAMA_CPP_DIR/build" --target llama-imatrix llama-quantize llama-perplexity -j

# 2. convert HF → f16 GGUF
# Resolve an interpreter rather than assuming `python`: Ubuntu 22.04 ships python3 with no
# unsuffixed alias, so a bare `python` here is a guaranteed "command not found". Prefer the
# workspace venv — the convert script needs torch/transformers/numpy, which only it has.
if [[ -x "$ML_ROOT/.venv/bin/python" ]]; then PY="$ML_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "✗ no python interpreter found — run \`uv sync --extra train\` in ml/" >&2; exit 1
fi
"$PY" "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" "$MODEL_DIR" --outfile "$F16_OUT" --outtype f16

# 3. importance matrix on BILINGUAL calibration text
"$LLAMA_CPP_DIR/build/bin/llama-imatrix" -m "$F16_OUT" -f "$CALIB_TXT" -o "$IMATRIX_OUT"

# 4. quantize Q4_K_M with imatrix
"$LLAMA_CPP_DIR/build/bin/llama-quantize" --imatrix "$IMATRIX_OUT" "$F16_OUT" "$Q4_OUT" Q4_K_M

echo "✓ GGUF written: $Q4_OUT"
echo "  next: just ppl-gate $Q4_OUT (ΔPPL ≤ 5% vs bf16 required for release)"
