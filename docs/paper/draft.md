# Sanad: A Reproducible Recipe for Bilingual Arabic/English Banking SLMs on One Consumer GPU, with Per-Language Quantization Gates

**Draft — ArabicNLP / OSACT workshop track.** Status: results sections 6.1–6.3 are measured;
6.4 (benchmarks) and 7 (judges) are incomplete and marked as such. Scope per CLAUDE.md §13 P7:
*recipe, harness, fertility/edge measurements.* **No frontier-beating claims.**

Every figure cites a report in `ml/evals/reports/` by sha256; see `RESULTS.md` §Traceability.

---

## Abstract

We report a reproducible recipe for adapting a 4B-parameter bilingual (Modern Standard Arabic /
English) instruction model to a narrow UAE retail-banking domain on a **single 24 GB consumer GPU
at zero marginal cost**, and for shipping it to two deployment shapes — a GPU server via AWQ-W4A16
and a **GPU-less commodity CPU** via GGUF Q4_K_M. Training completes in **44 minutes at 15.59 GB
peak VRAM**. Our central methodological contribution is a **per-language quantization gate**: we
show that reporting pooled perplexity delta conceals the failure mode that matters for Arabic, and
that with bilingual calibration (≥40% Arabic by character count) Arabic degrades *less* than English
under AWQ (**ΔPPL +1.44% vs +2.39%**). We also document a class of evaluation-harness defect we
believe is under-reported: a one-sided perplexity gate accepted a physically impossible **−39.5%**
result arising from a cross-runtime comparison. The resulting artifact answers Arabic and English
banking questions on a 12-core laptop with no GPU at **6.19 tok/s generation**. We make no claim
that this model matches larger general models in-domain; the evidence required for such a claim is
enumerated in §9 and was not collected.

---

## 1. Introduction

Sovereignty in Gulf financial deployments is usually discussed as policy. Treated instead as an
**engineering constraint** — zero network egress, on-premises weights, no third-party inference —
it produces concrete requirements: models small enough to run on hardware an institution already
owns, quantization that survives audit, and evaluation that can be re-run offline.

This paper does not ask whether a small model can beat a large one. It asks a narrower and more
answerable question: **what does the complete pipeline cost, and where does it silently break?**
We report the recipe, the measured envelope, and — at unusual length for a systems paper — the
defects encountered, because eight of ten lay in integration code that had never executed and were
invisible to linting, type checking, and unit tests.

**Contributions.**

1. A fully pinned, $0 recipe from raw data to two quantized deployment artifacts, reproducible on
   one 24 GB GPU (§4, §5).
2. A **per-language perplexity gate** and evidence that bilingual calibration inverts the expected
   Arabic penalty (§6.2).
3. A documented failure mode in perplexity gating — one-sided thresholds accept impossible
   improvements produced by cross-runtime measurement (§6.3).
4. Measured CPU-only edge economics for a 4B bilingual model, on hardware without a GPU (§6.4).

---

## 2. Related work

Arabic-native and Arabic-strong open models: ALLaM-7B-Instruct, the jais family, Falcon-H1-Arabic.
Evaluation: OALL-v2 native task suites, AraGen, and the 3C3H rubric with its correctness gate.
Efficient adaptation: QLoRA and DoRA. Post-training quantization: AWQ and the `compressed-tensors`
format vLLM consumes natively, and llama.cpp's k-quants with importance matrices.

Our departure is narrow: prior quantization work overwhelmingly reports **pooled** quality deltas.
For bilingual models we argue that is the wrong unit of measurement (§6.2).

---

## 3. Data and provenance

| source | records | provenance | licence |
|---|---|---|---|
| CIDAR (`arbml/CIDAR`) | 9,962 | native | Apache-2.0 |
| own banking pairs | 1,277 | **synthetic** | CC-BY-4.0 |
| total | **12,007** | native 86.52% / translated 0% / synthetic 13.48% | commercial-clean |

Language mix: **ar 90.39%, en 5.86%, mixed (code-switched) 3.75%.**

We treat **provenance as a first-class reported statistic**, not metadata. The 1,277 domain pairs
are machine-drafted and carry `provenance: synthetic` with no reviewer initials. This is stated
prominently rather than in an appendix because it bounds every domain-specific conclusion in the
paper: §6.4 shows a generated answer quoting **US dollars** for a UAE savings product, which is
precisely the failure an unreviewed synthetic corpus predicts.

A licence gate (`profile: commercial`) rejects any record outside {Apache-2.0, CC-BY-4.0, MIT} and
is tested against a planted non-commercial record. Splits are seeded (3407) and stratified by
`(lang, provenance)`, so held-out loss reflects the code-switched minority rather than averaging it
away.

---

## 4. Recipe

Base: `Qwen/Qwen3-4B-Instruct-2507` pinned at revision `cdbee75f17c01…` (Apache-2.0). QLoRA (NF4)
+ **DoRA**, r=16, α=16, dropout 0, applied to all seven linear projections
(`q,k,v,o,gate,up,down_proj` × 36 layers). Three epochs, effective batch 16, lr 2e-4 cosine, 3%
warmup, NEFTune α=5, seed 3407, non-thinking chat template.

The pipeline is pinned end to end: base-model revision must be a 40-character commit sha (a branch
or tag fails the gate), the lm-eval harness commit, and the llama.cpp commit are all fixed.

**Reproducibility caveat.** Unsloth caps TRL at `<=0.24.0` in every published release. A `trl>=1.0`
floor is therefore unsatisfiable alongside it, and a resolver with no upper bound on Unsloth
satisfies both constraints by silently selecting a year-old Unsloth that cannot import. We
recommend pinning the adaptation library's floor explicitly and **executing an import in
preflight**, since presence on disk does not imply an importable graph.

---

## 5. Training envelope

| metric | measured | target |
|---|---|---|
| wall time | **0.73 h** (44 min, 78 optimizer steps) | — |
| peak VRAM | **15.59 GB** | < 16 GB ✅ |
| cost | **$0** (local hardware) | < $50 ✅ |
| total FLOPs | 1.035 × 10¹⁷ | — |

| eval at epoch boundary | ep 1 | ep 2 | ep 3 |
|---|---|---|---|
| eval_loss | 1.79316 | 1.69111 | **1.67636** |

Train loss falls 2.6732 → 1.6888 over 78 steps; eval loss decreases monotonically at every epoch
boundary and tracks train loss closely, indicating no overfitting at this scale.

**We caution against over-reading this curve.** At 12k records with packing at 4096 tokens, three
epochs is only ~26 optimizer steps per epoch, making the 3% warmup roughly two steps. The schedule
is short and the curve coarse; it demonstrates the recipe runs and converges, not that this is a
well-tuned model.

---

## 6. Results

### 6.1 Artifacts

| artifact | size | runtime |
|---|---|---|
| merged bf16 | 7.6 GB | reference |
| AWQ-W4A16 (`compressed-tensors`) | **2.5 GB** | vLLM |
| GGUF Q4_K_M + bilingual imatrix | **2.32 GiB** | llama.cpp |

### 6.2 Per-language quantization gates — the main methodological result

Perplexity on a frozen 256-item bilingual holdout (226 ar / 20 en / 10 mixed), reported **per
language** rather than pooled.

| artifact | subset | baseline | quantized | ΔPPL |
|---|---|---|---|---|
| AWQ W4A16 | pooled | 6.871 | 6.972 | +1.48% |
| AWQ W4A16 | **Arabic** | 6.736 | 6.833 | **+1.44%** |
| AWQ W4A16 | English | 11.308 | 11.577 | +2.39% |
| GGUF Q4_K_M | pooled | 6.1415 | 6.2872 | +2.37% |
| GGUF Q4_K_M | **Arabic** | 6.2276 | 6.3765 | **+2.39%** |
| GGUF Q4_K_M | English | 6.8939 | 6.8369 | −0.83% |

With calibration constrained to **≥40% Arabic by character count** — characters, not records, since
English records are longer and a half-Arabic record split still under-represents Arabic tokens —
**Arabic degrades less than English under AWQ.** The pooled figure (+1.48%) would have concealed
both per-language numbers and, on an English-calibrated run, would plausibly have concealed Arabic
degradation entirely.

We therefore argue the per-language delta, not the pooled delta, is the correct release gate for
bilingual models. The cost is negligible: the same holdout, partitioned.

*Caveat:* the English partition is 20 records and is noisy. The AR-vs-EN ordering should be read as
"Arabic was not preferentially harmed", not as a precise effect size.

### 6.3 A failure mode in perplexity gating

Our first GGUF gate **passed** while reporting ΔPPL of −8.5% pooled and **−39.54%** on English:
4-bit quantization apparently outperforming f16. Two independent defects combined.

1. **Cross-runtime comparison.** The baseline was measured with a HuggingFace forward pass
   (per-document, truncated) and the candidate with `llama-perplexity` (one concatenated corpus,
   sliding windows). The delta measured the gap between two runtimes, not quantization loss.
2. **One-sided threshold.** The gate tested `delta > threshold`, so an impossible improvement
   passed as a success.

Both are trivially avoidable once named: measure both sides through the same binary, and make the
gate two-sided so a large negative delta **fails** with a diagnostic that the harness, not the
model, improved. We report this because the failure is silent, produces publishable-looking
numbers, and we have not seen it described in the quantization literature.

### 6.4 Edge economics — CPU-only

12-core x86_64 laptop, **no GPU**, 14 GB RAM, llama.cpp at the same pinned commit that produced the
GGUF.

| metric | value |
|---|---|
| prompt processing | **30.05 tok/s** |
| generation | **6.19 tok/s** |
| end-to-end via OpenAI-compatible server | ~4.7 tok/s |
| Arabic fertility, this tokenizer | **2.44 tokens/word** |
| package watts | — (RAPL unreadable without privilege) |

Qualitative behaviour: the model answers MSA Arabic and English banking prompts and **preserves
code-switching** — Latin `mobile banking app` remains intact inside an Arabic sentence, the 3.75%
minority case. Two defects are visible: the served model prefixes responses with stray
`<tool_call>` control tokens, and the domain answer quoting USD for an AED product (§3).

### 6.5 Standardized benchmarks — ArabicMMLU, no comparator

Both the fine-tuned model and its own base were scored with an identical command:
lm-evaluation-harness at `6d642546f4688648fced259eb3302efd36ece5af` (v0.4.12),
`--tasks arabicmmlu --num_fewshot 0 --seed 3407`, bf16, `max_model_len=8192`, vLLM 0.26.0, one
RTX 4090. 14,455 items over 45 subtasks.

| model | ArabicMMLU (0-shot) | stderr |
|---|---|---|
| `Qwen/Qwen3-4B-Instruct-2507` (base) | 59.79% | ±0.40 |
| this work, merged bf16 | 59.33% | ±0.40 |
| delta | **−0.46 pt** | σ_diff = 0.56 |

The delta clears the −1 pt catastrophic-forgetting threshold we set in advance, and it is **smaller
than the standard error of the difference** — i.e. indistinguishable from zero at 95%. The defensible
statement is therefore narrow: **1,277 synthetic banking pairs plus 9,962 CIDAR records, trained for
44 minutes at r=16, did not measurably degrade general Arabic knowledge.** All four ArabicMMLU
categories move down by 0.21–1.11 pt, each within its own interval; we read this as noise rather than
a domain-versus-general trade-off, and we do not claim the reverse either.

Two honest limits on this table. First, `aratrust`, `madinahqa` and `alrage` — named in our own
pinned-asset matrix as harness-provided — **do not exist at the pinned rev**, so the benchmark axis is
one task wide, not four. Second, **no comparator was measured**: parity with one's own base model on a
general benchmark is a regression check, and carries no information about the small-versus-large
question in §1. That question remains open, and §6.6 is where it would have been answered.

Practical note for anyone reproducing this: vLLM sizes its KV cache to the model's advertised
context, and Qwen3-4B advertises 262,144 tokens — 36 GiB of KV against the ~11.5 GiB free after
weights on a 24 GB card. The engine refuses to start, identically for every model, with an error that
names neither the context length nor the card. Pinning `max_model_len` is not an optimization here;
it is a precondition for the harness running at all on the hardware this recipe targets.

---

## 7. Evaluation harness (design, not results)

The harness implements a family-exclusion judge pool (never a judge from the tested model's
family), 3C3H with correctness as a binary gate, Krippendorff α and pairwise Cohen's κ for judge
disagreement, and a 50-item native-speaker validation whose human↔judge κ is treated as a
**publication gate** — no judge-based number may be reported without it.

**This protocol was implemented but not executed.** The domain evaluation set contains 12 of its
intended 300 items, and no human validation was performed. We report the design because we consider
the human-κ-as-gate discipline the part most worth adopting, and because publishing the protocol
without its results is more honest than publishing judge scores without the κ.

---

## 8. Engineering findings

Ten defects surfaced, of which eight lay in integration code that had never executed end to end and
none were detectable by linting, static typing, or unit tests. A representative selection:

| defect | lesson |
|---|---|
| `find_spec` in preflight reported 15/15 green one second before an ImportError | presence ≠ importability; execute the import |
| `target_modules="all-linear"` iterated into its own characters by the adaptation library | a library's documented shorthand may not survive a wrapper |
| adaptation library imported *after* the trainer it patches, so a patched model ran through the stock trainer | import order can be load-bearing; assert it statically |
| AWQ OOM because the quantizer auto-offloads only for MoE architectures | defaults tuned for one architecture family |
| release gate could not run because its binary was never built | gates must be exercised, not just written |
| transfer verifier reported six files missing due to `lstrip("./")` stripping leading dots | verify the verifier |

The last is instructive: it made a complete 22.41 GB transfer appear to have failed six files.
Because the irreversible deletion was **gated on** verification rather than run alongside it, the
outcome was a refusal to delete rather than data loss. Ordering guards before irreversible actions
converted a bug into an inconvenience.

---

## 9. Limitations

1. **One benchmark, no comparator** (§6.5). ArabicMMLU is measured for this model and its base;
   `aratrust`, `madinahqa` and `alrage` are absent from the pinned harness rev, and no larger or
   Arabic-native comparator was run — so no *relative* quality claim is available.
2. **No in-domain score.** The domain set holds 12/300 items; the small-versus-large question this
   project was designed around is unanswered.
3. **No judge results and no human κ** (§7).
4. **13.5% of training data is machine-drafted and unreviewed**, bounding every domain conclusion.
5. **MSA only.** No dialect coverage; Gulf dialect is the obvious next axis and is absent.
6. **Short schedule.** 78 optimizer steps (§5).
7. **English holdout partition is 20 records**, so §6.2's cross-language comparison is directional.
8. **Single seed, single run.** No variance estimates; every number is n=1.
9. **Artifact defects** (§6.4) make the model a demonstration, not a deployable system.

---

## 10. Reproducibility statement

Seed 3407 throughout. Pinned: base revision `cdbee75f17c01…`, llama.cpp `c0bc8591e` (b10107),
lm-eval `6d642546…`. Lockfiles for both Python workspaces and the web app are committed. Data
`MANIFEST.yaml` (sha256 `139e92e2…`) records per-source counts, licences, provenance split and
per-shard hashes; the training config hash `4a70cdc1…` is logged into the experiment tracker
alongside the resolved target-module list. Perplexity-gate reports and the edge benchmark are
committed with their sha256 in `RESULTS.md`. Code Apache-2.0; own data CC-BY-4.0.

**Not reproducible from this repository:** model weights (excluded by policy) and the base model
download, which requires network access.

---

## Artifact checklist (camera-ready)

- [x] configs + MANIFEST hashes table
- [x] quantization-gate reports archived + hashed
- [x] edge benchmark archived + hashed
- [x] model card
- [x] benchmark results (§6.5) — ArabicMMLU, fine-tuned + base, reports hashed
- [ ] comparator results (ALLaM-7B, jais-6.7b, a large generalist)
- [ ] cosign-signed artifacts on a registry
- [ ] human validation protocol + anonymized scores
