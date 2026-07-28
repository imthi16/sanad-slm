# Model Card — sanad-qwen3-4b-bank v0.1.0

> Every number here traces to a report in `ml/evals/reports/` by hash (working agreement #6).
> Fields that were not measured say so; none are estimated. **No frontier-beating claims.**
>
> **Status: not releasable.** Two of the four §5.5 release conditions are unmet — see
> [Release status](#release-status). This card documents a working artifact, not a shipped one.

## Summary

| | |
|---|---|
| Base model | `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f17c01a7cc42f958dc650907174af0554` (Apache-2.0) |
| Method | QLoRA (NF4) + DoRA, r=16 α=16, Unsloth 2026.7.5 + TRL 0.24, non-thinking chat template |
| Target modules | `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` (×36 layers) |
| Data | 12,007 records — **86.52% native / 0% translated / 13.48% synthetic**; MANIFEST sha256 `139e92e242548d009baeabc697f61ffb6c83b8859c793a0b73b2086c64503eec` |
| Train config sha256 | `4a70cdc191edc8cd6d77c15edafc579f82d6fc6845349cb1cfe482daec573fbc` |
| Train budget | **0.73 h** on 1×RTX 4090 (24 GB) · peak VRAM **15.59 GB** · **$0** (local compute, ADR-0004) |
| Schedule | 3 epochs = **78 optimizer steps**, effective batch 16, lr 2e-4 cosine, seed 3407 |
| Artifacts | merged-bf16 7.6 GB · AWQ-W4A16 2.5 GB · GGUF Q4_K_M 2.32 GiB (+ bilingual imatrix) |
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

### Standardized benchmarks — **not measured**

| Benchmark | Base | This model |
|---|---|---|
| ArabicMMLU | — | — |
| AraTrust | — | — |
| MadinahQA | — | — |
| ALRAGE | — | — |

lm-eval @ `6d642546f4688648fced259eb3302efd36ece5af` is pinned and wired, and the harness now runs
in an isolated venv, but P4 has not completed. **No comparator** (ALLaM-7B, jais-6.7b, or a large
generalist) was measured, so no relative claim of any kind exists.

### Domain eval — **not available**

`sanad_bank_eval_v1.jsonl` holds **12 of its 300 items**. No in-domain score exists, which is the
exact axis this project's thesis rests on. The headline *"matches a 5–10× larger model in-domain"*
is therefore **unavailable**, and no partial version of it is quoted anywhere.

### 3C3H judges — **not available**

No judges were run, and the 50-item native-speaker validation does not exist, so
**human↔judge κ is absent**. Prime directive 5 blocks every judge-based claim without it.

## Quantization gates — both PASSED

| artifact | subset | baseline | quantized | ΔPPL | gate |
|---|---|---|---|---|---|
| AWQ W4A16 | pooled | 6.871 | 6.972 | +1.48% | ≤3% ✅ |
| AWQ W4A16 | **Arabic** (n=226) | 6.736 | 6.833 | **+1.44%** | ≤3% ✅ |
| AWQ W4A16 | English (n=20) | 11.308 | 11.577 | +2.39% | ≤3% ✅ |
| GGUF Q4_K_M | pooled | 6.1415 | 6.2872 | +2.37% | ≤5% ✅ |
| GGUF Q4_K_M | **Arabic** (n=226) | 6.2276 | 6.3765 | **+2.39%** | ≤5% ✅ |
| GGUF Q4_K_M | English (n=20) | 6.8939 | 6.8369 | −0.83% | ≤5% ✅ |

Calibration was bilingual with ≥40% Arabic characters, enforced before the run — English-only
calibration measurably degrades Arabic, and **Arabic degraded less than English under AWQ**, which
is the intended effect. ArabicMMLU drop: **— (requires P4)**.

Reports: `ppl_gate_awq-w4a16.json`, `ppl_gate_sanad-Q4_K_M.gguf.json`.

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
| ppl gate | ✅ both artifacts, per-language |
| eval report attached | ❌ no benchmark or domain evaluation exists |
| cosign signature | ❌ not signed |

**Two of four unmet, so this version is not releasable** — and the artifact defects above would
block it independently.

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
