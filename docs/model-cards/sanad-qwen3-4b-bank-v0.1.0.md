# Model Card — sanad-qwen3-4b-bank v0.1.0

> Every number here traces to a report in `ml/evals/reports/` by hash (working agreement #6).
> Fields that were not measured say so; none are estimated. **No frontier-beating claims.**
>
> **Status: not releasable.** The cosign signature is missing and the eval condition is only
> partially met — ArabicMMLU is measured, the domain eval is not. See
> [Release status](#release-status-55). This card documents a working artifact, not a shipped one.

## Summary

| | |
|---|---|
| Base model | `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f17c01a7cc42f958dc650907174af0554` (Apache-2.0) |
| Method | QLoRA (NF4) + DoRA, r=16 α=16, Unsloth 2026.7.5 + TRL 0.24, non-thinking chat template |
| Target modules | `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` (×36 layers) |
| Data | 11,239 records — **88.64% native / 0% translated / 11.36% synthetic**; MANIFEST sha256 `433b95142b342d54fff3e38ccf706dcc2136336114e8c1dc3fac2b2d2bb1e3e7` |
| Train config sha256 | `4a70cdc191edc8cd6d77c15edafc579f82d6fc6845349cb1cfe482daec573fbc` |
| Train budget | **0.73 h** on 1×RTX 4090 (24 GB) · peak VRAM **15.59 GB** · **$0** (local compute, ADR-0004) |
| Schedule | 3 epochs = **78 optimizer steps**, effective batch 16, lr 2e-4 cosine, seed 3407 |
| Artifacts **shipped** | merged-bf16 7.6 GB · GGUF Q4_K_M 2.32 GiB (+ bilingual imatrix) |
| Artifacts **withheld** | AWQ-W4A16 2.5 GB — **fails its ArabicMMLU gate** (−1.75 pt vs bf16); kept as evidence, not a deliverable |
| Adapter sha256 | `d5e0bdf0afbe684d72668cf33d12245f57faaef5ce2a326cbb86783341f3642f` |
| GGUF sha256 | `d3d8a2d97b0abedb6fd00133722a680fcab6cb5efc5044e5be7aea41913d2b0f` |
| License | Apache-2.0 (derivative of an Apache-2.0 base; data CC-BY-4.0 / Apache-2.0 only) |
| Signature | **not signed** — cosign signing not yet run |

## Intended use & scope

UAE banking/compliance assistant, MSA Arabic + English + light code-switching. **Not** a
general-purpose model. **No dialect coverage in v1.** Not a substitute for compliance review.

**Do not deploy this version.** See [Known defects](#known-defects).

## Training

| step | 10 | 20 | 30 | 40 | 50 | 60 | 70 |
|---|---|---|---|---|---|---|---|
| train loss | 2.6732 | 1.9743 | 1.8088 | 1.7688 | 1.7094 | 1.6860 | 1.6888 |

| eval at epoch boundary | ep 1 | ep 2 | ep 3 |
|---|---|---|---|
| eval_loss | 1.79316 | 1.69111 | **1.67636** |

Monotone at every epoch boundary; eval tracks train closely, so no overfitting signal. **But 78
steps is a short schedule** (~26 steps/epoch at this corpus size, making `warmup_ratio: 0.03`
about two steps). Read the curve as coarse, not converged. MLflow run `b8ccaafc`.

## Evaluation

### Standardized benchmarks — **ArabicMMLU measured; the rest unavailable**

| Benchmark | Base (`Qwen3-4B-Instruct-2507`) | This model | Delta |
|---|---|---|---|
| ArabicMMLU (0-shot, 14,455 items) | **59.79%** ±0.40 | **59.33%** ±0.40 (bf16, shipped) | **−0.46 pt** |
| ArabicMMLU — AWQ W4A16 (withheld) | 59.79% ±0.40 | 57.58% ±0.40 | −2.21 pt |
| ArabicMMLU — **ALLaM-7B-Instruct-preview** (Arabic-native comparator, 7B) | — | **70.01%** ±0.37 | **+10.68 pt over this model** |
| AraTrust | — | — | not in the pinned harness rev |
| MadinahQA | — | — | not in the pinned harness rev |
| ALRAGE | — | — | not in the pinned harness rev |

lm-eval @ `6d642546f4688648fced259eb3302efd36ece5af` (v0.4.12), identical command for both models:
`--tasks arabicmmlu --num_fewshot 0 --seed 3407`, bf16, `max_model_len=8192`, vLLM 0.26.0 on one
RTX 4090. Run 2026-07-29. Reports: `finetuned/…/results_2026-07-29T09-41-07.704402.json`
(sha256 `1e7301d1…`) and `base/…/results_2026-07-29T09-49-43.877133.json` (sha256 `c758c32f…`).

`aratrust`, `madinahqa` and `alrage` are named in CLAUDE.md §15 as available via lm-eval; at this
pinned rev they are **not in the harness at all**, so they could not be run rather than merely being
skipped.

**Interpretation, stated conservatively.** −0.46 pt clears the §9.5 no-catastrophic-forgetting gate
(≥ base − 1.0 pt). It is also smaller than the 0.56 pt standard error of the difference, so it is
**statistically indistinguishable from zero**: the banking fine-tune left general Arabic knowledge
intact. This is *not* a quality improvement, and ArabicMMLU is not a benchmark where a narrow
domain SFT should be expected to produce one. Per category, all four move down by between 0.21 and
1.11 pt — each inside its own interval, which is the shape of noise rather than a trade-off.

**One comparator was measured, and this model loses to it.** ALLaM-7B-Instruct-preview scores
**70.01%** — 10.68 points above this model. That is the expected outcome: 1.75× the parameters and
Arabic-native pretraining, against a general-purpose 4B given 11,239 instruction records. The gap
is monotone in how much Arabic cultural/linguistic knowledge a category needs — **Humanities +19.99
pt, STEM only +1.53 pt** — which is what native pretraining actually buys.

It does not contradict this project's thesis (in-domain banking), but it does close off any reading
of these numbers as general Arabic competitiveness. **jais-6.7b was not measured** (gated repo, the
train box's HF account is unauthorised), and **no large generalist was measured** — so the
"matches a 5–10× larger model" claim remains unavailable, and the one comparator that does exist is
1.75× the size and wins.

### Domain eval — **not available**

`sanad_bank_eval_v1.jsonl` holds **12 of its 300 items**. No in-domain score exists, which is the
exact axis this project's thesis rests on. The headline *"matches a 5–10× larger model in-domain"*
is therefore **unavailable**, and no partial version of it is quoted anywhere.

### 3C3H judges — **not available**

No judges were run, and the 50-item native-speaker validation does not exist, so
**human↔judge κ is absent**. Prime directive 5 blocks every judge-based claim without it.

## Quantization gates — ΔPPL passed for both; **AWQ fails its accuracy clause**

§5.3 has two criteria. Both artifacts clear ΔPPL; AWQ does not clear ArabicMMLU.

### (a) ΔPPL — both PASSED

| artifact | subset | baseline | quantized | ΔPPL | gate |
|---|---|---|---|---|---|
| AWQ W4A16 | pooled | 6.871 | 6.972 | +1.48% | ≤3% ✅ |
| AWQ W4A16 | **Arabic** (n=226) | 6.736 | 6.833 | **+1.44%** | ≤3% ✅ |
| AWQ W4A16 | English (n=20) | 11.308 | 11.577 | +2.39% | ≤3% ✅ |
| GGUF Q4_K_M | pooled | 6.1415 | 6.2872 | +2.37% | ≤5% ✅ |
| GGUF Q4_K_M | **Arabic** (n=226) | 6.2276 | 6.3765 | **+2.39%** | ≤5% ✅ |
| GGUF Q4_K_M | English (n=20) | 6.8939 | 6.8369 | −0.83% | ≤5% ✅ |

Calibration was bilingual with ≥40% Arabic characters, enforced before the run, and **Arabic
degraded less than English under AWQ** — the intended effect of that requirement.

### (b) ArabicMMLU drop ≤ 1.0 pt — AWQ **FAILED**, GGUF **unmeasured**

| artifact | ArabicMMLU | vs bf16 parent | gate ≤ 1.0 pt |
|---|---|---|---|
| bf16 (parent) | 59.33% ±0.40 | — | — |
| **AWQ W4A16** | **57.58% ±0.40** | **−1.75 pt** | ❌ **FAIL** (3.1× σ_diff — a real regression) |
| GGUF Q4_K_M | — | — | **not measured** |

**Perplexity said this artifact was fine and the benchmark says it is not.** +1.44% Arabic ΔPPL is
under half the budget, yet accuracy fell 1.75 pt. A pipeline gated on perplexity alone would have
shipped it. **ΔPPL is not a sufficient proxy for downstream accuracy at 4-bit** — this is the single
most useful negative result in the project.

**AWQ is therefore withheld from the release path.** Shipping is bf16 + GGUF Q4_K_M.

**Stated plainly rather than buried:** the GGUF's ArabicMMLU clause is *unmeasured*, so AWQ is
excluded on a criterion the shipped GGUF has not faced. A same-bit-width scheme lost 1.75 pt, so
Q4_K_M plausibly loses something comparable. 14,455 items × 4 choices through llama.cpp on CPU is
many hours; the tractable route is a CUDA build or a declared stratified subsample. Until one is
run, the shipped GGUF carries the same unquantified risk AWQ was rejected for.

Reports: `ppl_gate_awq-w4a16.json`, `ppl_gate_sanad-Q4_K_M.gguf.json`,
`awq/awq-w4a16/…/results_2026-07-29T10-34-58.885145.json` (sha256 `8b045e3d…`).

## Efficiency — CPU-only edge, `platform: x86-local`

12-core x86_64 laptop, **no GPU**, llama.cpp `c0bc8591e` (b10107) — the same build that produced
the GGUF.

| metric | value |
|---|---|
| prompt processing | **30.05 tok/s** (`llama-bench -t 6 -p 64`) |
| generation | **6.19 tok/s** (`llama-bench -t 6 -n 32`) |
| end-to-end chat via `llama-server` | ~4.7 tok/s (includes prompt processing) |
| Arabic fertility, this tokenizer | **2.44 tokens/word** |
| watts | — (Intel RAPL present, unreadable without sudo) |

## Known defects

1. **Stray `<tool_call>` tokens prefix every response.** The Qwen3 chat template's tool-calling
   path emits control tokens with no tools defined. A client would have to strip them. Cause not
   isolated — serve-time template application, or a train/serve template mismatch.
2. **Domain answers are unvalidated, and at least one is wrong.** Asked for a UAE savings-account
   minimum balance, the model answered in **US dollars**. This is the predictable consequence of
   training on a 13.5% machine-drafted corpus with no native reviewer: fluent, well-formed, wrong
   on the specifics that matter.

## Release status (§5.5)

| condition | state |
|---|---|
| licence gate | ✅ `profile: commercial`, all sources Apache-2.0 / CC-BY-4.0 |
| ppl gate | ⚠️ **ΔPPL ✅ both artifacts; AWQ fails the ArabicMMLU clause (−1.75 pt) and is withheld. GGUF's clause is unmeasured** |
| eval report attached | ⚠️ **partial** — ArabicMMLU measured for this model, its base and one comparator (ALLaM-7B, which wins by 10.68 pt — § Evaluation); no domain eval (12/300 items), no judges, no 5–10× generalist |
| cosign signature | ❌ not signed |

**Still not releasable.** The signature is absent outright, and the eval condition is only half met:
a general-benchmark forgetting check is not the domain evaluation §5.5 asks for. The artifact defects
above would block release independently.

## Reproduction

```bash
just preflight                       # 15 checks incl. a real import of the training stack
just train                           # 44 min on one RTX 4090, <16 GB peak
just merge
just quant-awq && just ppl-gate out/awq-w4a16
just quant-gguf && just ppl-gate out/sanad-Q4_K_M.gguf
just bench-edge                      # native llama-bench, no Docker needed
```

Full run narrative, including the ten defects found in never-executed code, is in
[`RESULTS.md`](../../RESULTS.md).
