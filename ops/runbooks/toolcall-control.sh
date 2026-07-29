#!/usr/bin/env bash
# The control that was missing from every previous <tool_call> investigation:
# does the BASE model do it too?
#
# Every earlier test varied the artifact (GGUF vs AWQ) or the prompt form (raw vs ChatML) but always
# used OUR fine-tune, so "the fine-tune causes it" was never actually tested. This runs the same
# 2-cell prompt matrix against base and fine-tuned bf16, same seed, same decode params, same
# template source. Four cells, one conclusion.
#
#   base + raw          base + template
#   finetuned + raw     finetuned + template
#
# If base+template leaks, the defect is upstream Qwen3 behaviour and the model card's "known defect"
# is mis-attributed. If only finetuned+template leaks, it is ours and lives in training.
set -uo pipefail
LOG="$HOME/sanad-toolcall-control.log"
exec >>"$LOG" 2>&1
echo; echo "===== toolcall control started $(date -Is) ====="

export PATH="$HOME/sanad-slm/ml/.venv-eval/bin:$HOME/.local/bin:$PATH"   # ninja lives here
export HF_HOME="$HOME/sanad-hf"
cd "$HOME/sanad-slm" || exit 1

# Refuse to fight another job for the card.
for _ in $(seq 1 60); do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  [ "$used" -lt 2000 ] && break
  echo "waiting for GPU (${used} MiB in use) $(date +%H:%M:%S)"; sleep 60
done

"$HOME/sanad-slm/ml/.venv-eval/bin/python" - <<'PY'
import json

from transformers import AutoTokenizer
from vllm import LLM, SamplingParams

MODELS = {
    "base": "Qwen/Qwen3-4B-Instruct-2507",
    "finetuned": "ml/out/merged-bf16",
}
Q = "ما هي أنواع الحسابات المصرفية المتاحة؟"
SPECIALS = ("<tool_call>", "</tool_call>", "<think>", "</think>")
results = {}

for label, path in MODELS.items():
    tok = AutoTokenizer.from_pretrained(path)
    templated = tok.apply_chat_template(
        [{"role": "user", "content": Q}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False,
    )
    llm = LLM(model=path, dtype="bfloat16", gpu_memory_utilization=0.80, max_model_len=8192)
    # Greedy AND sampled: the p5 demo leaked at temperature, so decode params must not be the story.
    for decode, sp in (
        ("greedy", SamplingParams(temperature=0.0, max_tokens=100, seed=3407)),
        ("sampled", SamplingParams(temperature=0.7, top_p=0.8, max_tokens=100, seed=3407)),
    ):
        for form, prompt in (("raw", Q), ("template", templated)):
            text = llm.generate([prompt], sp)[0].outputs[0].text
            results[f"{label}|{decode}|{form}"] = {
                "leaks": any(s in text for s in SPECIALS),
                "found": [s for s in SPECIALS if s in text],
                "head": text[:110].replace("\n", "\\n"),
            }
    del llm
    import gc

    import torch
    gc.collect()
    torch.cuda.empty_cache()

print("=== MATRIX ===")
for k, v in results.items():
    print(f"{k:34s} leaks={str(v['leaks']):5s} {','.join(v['found']) or '-':24s} {v['head'][:70]}")
print("\n=== JSON ===")
print(json.dumps(results, ensure_ascii=False, indent=2))

base_t = results.get("base|greedy|template", {}).get("leaks")
ft_t = results.get("finetuned|greedy|template", {}).get("leaks")
print("\n=== VERDICT ===")
if base_t and ft_t:
    print("UPSTREAM: base leaks too — not caused by our fine-tune; the model card must be corrected.")
elif ft_t and not base_t:
    print("OURS: only the fine-tune leaks — the cause is in training, not packaging or the template.")
elif not ft_t and not base_t:
    print("NEITHER leaks here — the leak is specific to the serving path (GGUF/llama.cpp or the API).")
else:
    print("base leaks but fine-tune does not — fine-tuning suppressed an upstream behaviour.")
PY
rc=$?
echo "--- python exit: $rc ---"
cp "$LOG" "$HOME/sanad-slm/ml/evals/reports/toolcall_control.txt" 2>/dev/null
echo "===== toolcall control done $(date -Is) ====="
