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
cmake -S "$LLAMA_CPP_DIR" -B "$LLAMA_CPP_DIR/build" -DGGML_CUDA="${GGML_CUDA:-ON}"
cmake --build "$LLAMA_CPP_DIR/build" --target llama-imatrix llama-quantize -j

# 2. convert HF → f16 GGUF
python "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" "$MODEL_DIR" --outfile "$F16_OUT" --outtype f16

# 3. importance matrix on BILINGUAL calibration text
"$LLAMA_CPP_DIR/build/bin/llama-imatrix" -m "$F16_OUT" -f "$CALIB_TXT" -o "$IMATRIX_OUT"

# 4. quantize Q4_K_M with imatrix
"$LLAMA_CPP_DIR/build/bin/llama-quantize" --imatrix "$IMATRIX_OUT" "$F16_OUT" "$Q4_OUT" Q4_K_M

echo "✓ GGUF written: $Q4_OUT"
echo "  next: just ppl-gate $Q4_OUT (ΔPPL ≤ 5% vs bf16 required for release)"
