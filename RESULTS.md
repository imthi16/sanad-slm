# SANAD — measured results, run of 2026-07-26 → 28

> **This is a personal portfolio and research project.** It is not a product, was not built for a
> client, and is not deployed anywhere — there is no production use and no service-level commitment.
> Its purpose is to demonstrate a reproducible Arabic/English fine-tuning and quantization recipe
> end to end on one consumer GPU, and it is the evidence base for a workshop paper draft
> ([`docs/paper/`](docs/paper/)) scoped per §13 P7 to the *recipe, harness and fertility/edge
> measurements* — explicitly **no frontier-beating claims**.
>
> That context sets the scope, not the standard. The measurements below are real and reproducible,
> and the gaps are labelled honestly — a portfolio piece that overstates its evidence is worth less
> than one that shows exactly how far it got.

Every number here traces to a file produced by the pipeline (prime directive 6). Figures that were
not measured are written `—`, never estimated (§8.2). Read the
[Scope and limits](#6-scope-and-limits--what-this-run-does-not-show) section before quoting anything.

**Compute:** one RTX 4090 (24 GB) on an x86_64 Linux workstation for training and AWQ; a separate
CPU-only 12-core laptop for the edge measurements. **Cost: $0** — local hardware (ADR-0003/0004).

### Traceability (prime directive 6)

Every figure below comes from one of these, committed alongside this document. `ml/evals/reports/**`
is gitignored for bulk output, so these four were force-added: they are the evidence, and a claim
whose evidence is untracked is not a claim.

| report | sha256 |
|---|---|
| `ppl_gate_awq-w4a16.json` | `5176c719732c5079c2cab01540e22bb514ac9d6497afadd0fd9054847e937aac` |
| `ppl_gate_sanad-Q4_K_M.gguf.json` | `c195e7447d2e00f5e0a09a0c27eb50c6b94912cb033148fb8966ec30535d21ef` |
| `edge_bench_x86-local.txt` | `3fa61ce6c4261e3629c20ab6d5ac415839c1b1b707b0456b1786d4e3149ef7c8` |
| `demo_x86-local.json` | `f3659759e260dbbc02dc6f403d11e57ac19781e0e6e0fe78a4b15f62601fde5a` |
| `finetuned/merged-bf16/…/results_2026-07-29T09-41-07.704402.json` | `1e7301d1cadc7e6947dd2d2ab28b10f8404787f17d0ed6ac9b69c3f124ed21d6` |
| `finetuned/merged-bf16/PROVENANCE.yaml` | `bdb441204f704c8475f857a6e16128d933588f90e3af0ac3f35d0d2cc478a2d8` |
| `base/Qwen3-4B-Instruct-2507/…/results_2026-07-29T09-49-43.877133.json` | `c758c32fb7944b981816382fe7ac8b5eed9cab881c3bc1691913bec238c2bcf9` |
| `base/Qwen3-4B-Instruct-2507/PROVENANCE.yaml` | `7424e24a8a0bb56c1bc8d3d008c2d03bfdca064cae4d574345ef9bd4216a07a4` |
| `awq/awq-w4a16/…/results_2026-07-29T10-34-58.885145.json` | `8b045e3d5b7ecb68c648f54d660b51442c5a34e58e9fabcf0b1af94af32492af` |
| `awq/awq-w4a16/PROVENANCE.yaml` | `9c7f179bb738f830d2e3671a6d7e5834f93c69a136f59bd537875ea80fe0bc6c` |
| `comparator-allam/…/results_2026-07-29T11-10-20.827214.json` | `c9c08310442e3706e4aa421a978a715ca6237b43e857becb8c10c05b78a7ac86` |
| `comparator-allam/ALLaM-7B-Instruct-preview/PROVENANCE.yaml` | `3421f7d7bed46f6f9554987b956e0f3e39bb24d2feafeb7c4b58ef7a7aa6c9d0` |
| `train_metrics_b8ccaafc.json` | `1db671194bd7ff3094c6b9813c8b806a35bbd403abbaeed983b68ce6e9ba1865` |

The two `log_samples` trees (52,291 per-sample records per model, 44 MB each) are **not** committed;
they stay in `~/sanad-artifacts/`. The `results*.json` above hold every aggregate quoted in §5.

**Training metrics** (peak VRAM, wall time, FLOPs, the full loss curve) come from MLflow run
`b8ccaafc` (`hilarious-shad-242`, experiment `sanad-sft`). MLflow's backing store is a SQLite file
that is *not* in git, so the run is exported into the last row of the table above —
`train_metrics_b8ccaafc.json`, produced by `just export-metrics b8ccaafc` and force-added like the
rest. Every §4 figure is read from that file. The export is byte-deterministic (sorted keys, no
generation timestamp), so re-running it on the same run reproduces the same sha256; a report whose
hash moved on every export could not be cited by hash at all.

**Model weights are not in git** (prime directive 6) — the archive lives at `~/sanad-artifacts/`
with all 8,223 files sha256-verified against the machine that produced them.

---

## 1. Provenance and honesty summary

This matters more than the metrics, so it goes first.

| Claim | Available? | Why |
|---|---|---|
| Reproducible QLoRA recipe on one 24 GB GPU | **yes** | full config + lockfiles + pinned base revision; peak VRAM measured |
| Quantization preserves Arabic *perplexity* | **yes, both artifacts** | ΔPPL per language on a fixed held-out shard |
| Quantization preserves Arabic *accuracy* | **NO for AWQ, unmeasured for GGUF** | AWQ drops **−1.75 pt** on ArabicMMLU vs bf16 — fails §5.3's 1.0 pt budget; AWQ is therefore **not shipped** (§4) |
| CPU-only edge deployment works | **yes** | GGUF Q4_K_M runs under llama.cpp at the pinned commit |
| "Matches a 5–10× larger model in-domain" | **NO** | domain eval holds 12 of 300 items; and no 5–10× generalist was measured — the one comparator that ran, ALLaM-7B, is 1.75× |
| ArabicMMLU, fine-tuned **and** base, same pinned command | **yes** | 0-shot, 14,455 items, harness `6d642546…`; §5 |
| No catastrophic forgetting on ArabicMMLU | **yes** | −0.46 pt vs base, inside the §9.5 −1 pt gate *and* inside noise |
| AraTrust / MadinahQA / ALRAGE | **NO** | not present in the pinned harness rev at all (§5) |
| Any *relative* quality claim vs a larger model | **yes — and it is a loss** | ALLaM-7B (1.75×, Arabic-native) beats this model by **10.68 pt** on ArabicMMLU; §5. No 5–10× generalist was measured |
| Any judge-based (3C3H) claim | **NO** | no judges run, and no human-κ sample exists |

**The training corpus is 11.4% machine-drafted with no human reviewer.** Those records carry
`provenance: synthetic` honestly, but it means the domain adaptation is trained on text no
native speaker has validated. That alone blocks the headline claim, independent of P4.

**Corpus figures were corrected on 2026-07-29 and are lower than previously published.** Earlier
drafts of this document reported 12,007 records, an 86.52/13.48 provenance split and
`ar 90.39 / en 5.86 / mixed 3.75`. Those counted the two *derived* shards —
`calib_bilingual_512.jsonl` (512) and `ppl_heldout_bilingual.jsonl` (256) — which §5.1 draws **from
train and val**, so 768 records were counted twice and the language split was skewed by
calibration's deliberately English-heavier sample. The true corpus is **11,239 unique records**.
`manifest.py` now excludes derived shards from the census. Nothing downstream changes — training
always read `splits/train.jsonl` (10,676), never the inflated census.

**Two related defects found at the same time, both now fixed:** the per-source `provenance` field was
a hand-written literal declaring `sanad-bank-pairs` as `native` while all 1,277 of its records are
`synthetic` (prime directive 3 — it is now derived from the records); and the repository shipped the
**unpopulated MANIFEST template** for all of P1–P5, so `just data-gate` passed while asserting nothing
(`records=0`) and every eval report stamped that template's sha256 as `data_manifest_sha256`. The
gate now refuses a manifest with zero records, and the populated manifest is committed.

**Traceability caveat this creates:** the four eval reports in the table above carry
`data_manifest_sha256: 139e92e2…`, which is the hash of the **empty template**, not of the corpus
they were run against. The corpus manifest is `433b9514…`. The reports' benchmark numbers are
unaffected — they never read the manifest — but that lineage field does not identify the data until a
future run re-stamps it.

---

## 2. Data (P1) — `ml/data/MANIFEST.yaml`

| | records | provenance | licence |
|---|---|---|---|
| CIDAR (`arbml/CIDAR`) | 9,962 | native | Apache-2.0 |
| sanad-bank-pairs (own) | 1,277 | **synthetic** | CC-BY-4.0 |
| **total** | **11,239** | | `profile: commercial` gate ✅ |

Provenance split: **native 88.64% · translated 0% · synthetic 11.36%**
Language split: **ar 92.62% · en 3.53% · mixed 3.85%**

Derived shards: `splits/train.jsonl` 10,676 · `splits/val.jsonl` 563 (seeded 3407, stratified by
`(lang, provenance)`) · `calib_bilingual_512.jsonl` 512 · `ppl_heldout_bilingual.jsonl` 256
(226 ar / 20 en / 10 mixed).

The licence gate blocks a planted non-commercial record; AraFinNews stays quarantined.

---

## 3. Fine-tuning (P2) — `ml/configs/train/qwen3-4b-qlora-dora.yaml`

Base **`Qwen/Qwen3-4B-Instruct-2507`** pinned at revision
`cdbee75f17c01a7cc42f958dc650907174af0554` (Apache-2.0). QLoRA NF4 + **DoRA**, r=16, α=16,
dropout 0, 3 epochs, effective batch 16, lr 2e-4 cosine, warmup 3%, NEFTune α=5, seed 3407.

`target_modules: all-linear` resolved to the seven Qwen3 projections, recorded in MLflow:
`q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` (×36 layers).

### Acceptance criteria (§13 P2)

| Metric | Measured | Gate | |
|---|---|---|---|
| peak VRAM | **15.59 GB** | < 16 GB | ✅ |
| cost | **$0** (local) | $0 target | ✅ |
| wall time | 44 min (0.733 h), 78 optimizer steps | — | |
| total FLOPs | 1.035 × 10¹⁷ | — | |

Every cell above, and both loss tables below, read from `train_metrics_b8ccaafc.json`
(hashed in the traceability table): `peak_vram_gb: 15.594489344`, `train_runtime: 2636.3189` s of
training loop (`train_hours: 0.7327`), `total_flos: 1.0353e17`. Wall clock for the whole process was
3,315 s — the extra 11 minutes are model load, merge and save, which is why the *training* figure is
the one quoted. Cost is `$0`: no compute was purchased. MLflow also logs a `cost_usd` metric, which
is a cloud-equivalent estimate at `SANAD_GPU_USD_HR` (default $0.60/h) and is deliberately left out
of the export so it can never be misread as a spend.

### Loss

| step | 10 | 20 | 30 | 40 | 50 | 60 | 70 |
|---|---|---|---|---|---|---|---|
| train | 2.6732 | 1.9743 | 1.8088 | 1.7688 | 1.7094 | 1.6860 | 1.6888 |

| eval (epoch boundary) | ep 1 (step 26) | ep 2 (step 52) | ep 3 (step 78) |
|---|---|---|---|
| eval_loss | 1.79316 | 1.69111 | **1.67636** |

Monotone at every epoch boundary, and eval tracks train closely — no overfitting signal across
3 epochs. **Caveat: 78 steps is a short schedule** (≈26 steps/epoch at this corpus size, so
`warmup_ratio: 0.03` is ~2 steps). The curve is coarse and should not be read as finely converged.

Artifacts: `out/adapter` 146 MB · `out/merged-bf16` 7.6 GB (+ `manifest.json` lineage).

---

## 4. Quantization (P3)

| artifact | size | from |
|---|---|---|
| `out/awq-w4a16` (compressed-tensors, vLLM-native) | **2.5 GB** | 7.6 GB bf16 |
| `out/sanad-f16.gguf` | 8.05 GB | 7.6 GB bf16 |
| `out/sanad-Q4_K_M.gguf` (+ bilingual imatrix) | **2.50 GB** | f16 GGUF |

llama.cpp pinned at `c0bc8591e8815c63cb01dd3f051a8b0df02501c9` (release **b10107**), built
**CPU-only** — the box has an NVIDIA driver but no nvcc, which is also the honest edge story.

### AWQ quality gate — **FAILED** · `evals/reports/ppl_gate_awq-w4a16.json` + `evals/reports/awq/`

§5.3's gate has **two** criteria. AWQ passes the first and fails the second, which is the entire
reason the second exists.

**(a) ΔPPL ≤ 3% — PASSED.** Perplexity on the fixed 256-item bilingual holdout, quantized vs bf16,
both via transformers.

| subset | bf16 | AWQ W4A16 | ΔPPL | gate ≤ 3% |
|---|---|---|---|---|
| pooled | 6.871 | 6.972 | **+1.48%** | ✅ |
| **Arabic** (n=226) | 6.736 | 6.833 | **+1.44%** | ✅ |
| English (n=20) | 11.308 | 11.577 | +2.39% | ✅ |

Arabic degraded less than English — evidence the ≥40%-Arabic calibration requirement did its job
(§5.3 calls English-only calibration the most common silent failure mode). The English subset is
only 20 records and noisy; do not read the AR-vs-EN gap itself as meaningful.

**(b) ArabicMMLU drop ≤ 1.0 pt — FAILED.** Measured 2026-07-29, identical harness command to §5.

| model | ArabicMMLU (0-shot, 14,455 items) | stderr |
|---|---|---|
| fine-tuned bf16 | 59.33% | ±0.40 |
| **AWQ W4A16** | **57.58%** | ±0.40 |
| **drop** | **−1.75 pt** (budget −1.00) | σ_diff 0.56 |

The drop is **3.1× the standard error of the difference**, so it is a real regression, not noise.
Against the *base* model AWQ is −2.21 pt, which also breaks the §9.5 no-forgetting threshold that
the bf16 fine-tune passed comfortably.

**This is the headline methodological result of P3+P4, and it is a negative one.** Perplexity said
the quantization was fine — +1.44% Arabic, less than half the budget — and the benchmark says it is
not. **ΔPPL is not a sufficient proxy for downstream accuracy at 4-bit.** A pipeline gated on
perplexity alone would have shipped this artifact, and the only reason it was caught is that §5.3
specifies both criteria. The gate fired; it is being respected.

**Consequence: AWQ is not shipped.** The release path is **bf16 (`merged-bf16`) + GGUF Q4_K_M** only.
The AWQ artifact stays in the archive as measured evidence, not as a deliverable.

**Honest asymmetry, stated rather than buried:** the GGUF's ArabicMMLU clause is **unmeasured** (see
§4's GGUF gate below). AWQ is excluded on a criterion the GGUF has not been tested against, and
given a same-bit-width scheme lost 1.75 pt, Q4_K_M may well lose something similar. Measuring it
needs llama.cpp with GPU offload — 52,291 requests at the CPU edge box's ~30 tok/s prompt throughput
is many hours, which is why it has not been done rather than an oversight.

### GGUF Q4_K_M quality gate — ΔPPL PASSED, ArabicMMLU **unmeasured** · `evals/reports/ppl_gate_sanad-Q4_K_M.gguf.json`

Both sides through `llama-perplexity`, candidate against the **f16 GGUF**.

| subset | f16 GGUF | Q4_K_M | ΔPPL | gate ≤ 5% |
|---|---|---|---|---|
| pooled | 6.1415 | 6.2872 | **+2.37%** | ✅ |
| **Arabic** (n=226) | 6.2276 | 6.3765 | **+2.39%** | ✅ |
| English (n=20) | 6.8939 | 6.8369 | −0.83% | ✅ |

**This number was wrong the first time and the gate passed it anyway.** The initial run reported
−8.5% pooled and −39.5% English — 4-bit apparently beating f16, which is impossible. Two defects
combined: the baseline was measured with transformers while the candidate went through
`llama-perplexity` (different tokenization, different context windowing), and the threshold was
one-sided so an implausible "improvement" sailed through. Both are fixed: a GGUF candidate is now
compared against the f16 GGUF via the same binary, and a delta below −2% **fails** with the
explanation that the harness improved rather than the model. The AWQ gate was never affected —
both of its sides always went through transformers.

**Its ArabicMMLU clause was never run.** Q4_K_M ships with only half its gate evaluated. Scoring
14,455 items × 4 choices through llama.cpp on CPU is many hours at ~30 tok/s prompt throughput; the
tractable route is a CUDA llama.cpp build (the box has no nvcc, but Docker with GPU passthrough
works there), or a declared stratified subsample labelled as such. Until then, the shipped GGUF
carries the same unquantified risk that AWQ was rejected for — a gap, not a clean bill of health.

Worth keeping in mind when reading any quantization result: a gate that only checks one direction
cannot tell a good model from a broken measurement.

### Edge efficiency — CPU-only, `platform: x86-local`

Measured on the deployment target itself: 12-core x86_64 laptop, **no GPU**, 14 GB RAM, llama.cpp
at the pinned commit `c0bc8591e` (release b10107) — the same build that produced the GGUF.

| metric | value | how |
|---|---|---|
| prompt processing | **30.05 tok/s** | `llama-bench -t 6 -p 64` |
| generation | **6.19 tok/s** | `llama-bench -t 6 -n 32` |
| end-to-end chat | **~4.7 tok/s** | `llama-server` `/v1/chat/completions`, includes prompt processing |
| model size on disk | 2.32 GiB (4.02 B params) | Q4_K_M |
| watts | — | Intel RAPL present but unreadable without sudo |

The two throughput figures measure different things and should not be quoted interchangeably:
`llama-bench` isolates generation, the server figure is what a user experiences.

### Working demo — `sanad-artifacts/demo.json`

Three prompts through `llama-server`'s OpenAI-compatible endpoint (§6.2), seed 3407, temp 0.7:

| lang | response (excerpt) |
|---|---|
| ar | عادةً ما يبدأ الحد الأدنى للرصيد لفتح حساب توفير بـ 100 دولار أمريكي |
| en | To open a corporate bank account in the UAE… valid company registration certificate… articles of association… |
| mixed | نعم، يمكن استخدام الـ **mobile banking app** لتحويل الأموال دولياً |

The code-switched case works: Latin `mobile banking app` stays intact inside Arabic script, which
is the 3.85% of the corpus that is hardest to get right.

**Two defects are visible in that output and are not cropped out here:**

1. **Stray `<tool_call>` tokens prefix every response.** The Qwen3 chat template's tool-calling
   path emits control tokens even with no tools defined. A client would have to strip them, so the
   artifact is not yet fit to serve. Cause not yet isolated — template application at serve time,
   or a train/serve template mismatch.
2. **The Arabic answer quotes "100 دولار أمريكي" (US dollars) for a UAE savings account.** It
   should be AED. This is exactly the failure mode a 13.5%-machine-drafted, unreviewed corpus
   predicts: fluent, well-formed, and wrong on the domain specifics that matter. It is evidence
   *for* the provenance caveats in §1, not against them.

---

## 5. Standardized benchmarks (P4) — ArabicMMLU

Both models scored with the **identical** command (§5.4a): lm-evaluation-harness pinned at
`6d642546f4688648fced259eb3302efd36ece5af` (v0.4.12), `--tasks arabicmmlu`, **0-shot**, seed 3407,
`max_model_len=8192`, `gpu_memory_utilization=0.85`, bf16, vLLM 0.26.0 on one RTX 4090.
14,455 items across 45 subtasks. Run 2026-07-29, ~7 min of scoring per model.

| model | params | ArabicMMLU acc | stderr | vs our bf16 |
|---|---|---|---|---|
| **`humain-ai/ALLaM-7B-Instruct-preview`** (Arabic-native comparator) | 7B | **70.01%** | ±0.37 | **+10.68 pt** |
| `Qwen/Qwen3-4B-Instruct-2507` (base, rev `cdbee75f…`) | 4B | 59.79% | ±0.40 | +0.46 pt |
| `sanad-qwen3-4b-bank` merged-bf16 (**shipped**) | 4B | **59.33%** | ±0.40 | — |
| `sanad-qwen3-4b-bank` AWQ W4A16 (**not shipped**, §4) | 4B | 57.58% | ±0.40 | −1.75 pt |

**ALLaM-7B beats our model by 10.68 points on ArabicMMLU, and that is the expected result.** It is
1.75× the parameters and Arabic-native by pretraining, against a general-purpose 4B given 11,239
instruction records. Nothing in this project's thesis predicted otherwise: the claim was always
about *in-domain banking*, and ArabicMMLU is general Arabic knowledge. Reporting it prominently
rather than burying it is the point of running a comparator at all.

Where the gap sits is more informative than its size:

| category | ALLaM-7B | our bf16 | gap |
|---|---|---|---|
| **Humanities** | 74.70% | 54.71% | **+19.99** |
| Language | 73.57% | 60.81% | +12.76 |
| Other | 74.15% | 63.08% | +11.07 |
| Social Science | 66.55% | 58.42% | +8.13 |
| **STEM** | **63.42%** | **61.89%** | **+1.53** |

The gap is not uniform — its ordering tracks **how much Arabic cultural and linguistic knowledge the
category requires**. Humanities is a 20-point rout; STEM is +1.53 pt (~1.3σ, i.e. barely
distinguishable).

**That ordering is an observation, and this run cannot explain it.** ALLaM-7B and our model differ
in parameter count, family, architecture, pretraining corpus and instruction tuning simultaneously,
and these reports hold category accuracies and standard errors — no pretraining ablation, no
cross-language-transfer measurement. So "an Arabic-native corpus buys humanities and maths transfers
across languages" is a *hypothesis the table is consistent with*, not a result: a scale effect that
bites hardest on knowledge-heavy subtasks predicts the same shape. Isolating the cause needs one
architecture at one scale with the pretraining mixture varied, which was not run.

The structure is still a better finding than the headline delta, and it is exactly the kind of
observation a pooled single number would have destroyed — the same argument this project makes for
per-language quantization gates, arriving independently on the benchmark side.

**§9.5 no-catastrophic-forgetting gate: PASSED for bf16** (requires ≥ base − 1.0 pt). **The AWQ
artifact fails it** at −2.21 pt, and separately fails §5.3's quantization clause at −1.75 pt vs its
own bf16 parent — which is why the release path is bf16 + GGUF only.

The honest reading is *narrower* than the gate: the standard error of the difference is 0.56 pt, so
a −0.46 pt change is **statistically indistinguishable from zero** (95% interval ±1.10 pt). This
result says the banking fine-tune **did not damage** general Arabic knowledge. It does **not** show
an improvement, and ArabicMMLU is not the benchmark where a domain SFT should show one.

| category | fine-tuned | base | delta |
|---|---|---|---|
| Language | 60.81% | 61.60% | −0.79 |
| Other | 63.08% | 63.49% | −0.41 |
| Social Science | 58.42% | 59.53% | −1.11 |
| STEM | 61.89% | 62.10% | −0.21 |

Every category moves down slightly and every move is within its own confidence interval — the
signature of noise, not of a systematic trade. Largest per-subtask swings, listed because they are
mostly small-*n* subtasks and should not be over-read: `arabic_language_middle_school` **+11.11**,
`math_primary_school` +2.93, `arabic_language_grammar` +2.74 · `arabic_language_general` **−4.58**,
`computer_science_middle_school` −3.70, `geography_primary_school` −3.51.

**What this section does not contain.** `aratrust`, `madinahqa` and `alrage` are named in
CLAUDE.md §15 as available "via lm-eval tasks"; at this pinned rev they **do not exist in the
harness** (grepped, not assumed), so only ArabicMMLU could be run. **jais-family-6.7b-chat was not
measured** — it is `gated: auto` and the train box's Hugging Face account is not on the authorised
list, which needs a human to accept the terms once; the run 403'd. **No large generalist was
measured**, so the "matches a 5–10× larger model" claim remains unavailable: ALLaM-7B is 1.75× our
size, not 5–10×, and it *wins*. The other half of the §9.5 gate — domain ≥ base +5 pts — remains
unevaluable while the domain set holds 12/300 items, which is also the only axis on which this
project ever claimed to compete.

Three attempts were needed to get here; the two bugs are recorded in §7 rather than hidden, because
both were failures of *our* harness, not of the models.

---

## 6. Scope and limits — what this run does **not** show

Most of these are *scope boundaries of a portfolio project*, not defects: a comparator matrix and a
human-validated judge protocol are weeks of work and, for items 3 and 4, another person's time.
They are listed so nothing here is mistaken for more than it is.

1. **Benchmarks cover ArabicMMLU only** (§5). `aratrust`, `madinahqa` and `alrage` are absent from
   the pinned harness rev, so half of §15's benchmark list could not be run at all. Of the §9.5
   regression gate, the ArabicMMLU half is now **evaluated and passed**; the domain half
   (≥ base +5 pts) remains unevaluable — see item 3.
2. **One comparator, and this model loses to it.** ALLaM-7B was measured and **wins by 10.68 pt**
   (§5). jais-6.7b is a gated repo whose terms were never accepted, and no large generalist was
   run; Falcon-H1 has no exact repo id pinned in §15 and was dropped rather than guessed. The
   headline "matches a 5–10× larger model" is therefore still unavailable — the one comparator
   that ran is **1.75×, not 5–10×**, and ArabicMMLU parity with *its own base model* is a
   forgetting check, not a size comparison.
3. **Domain eval is 12 of 300 items.** No in-domain score is available, which is precisely the
   axis the project's thesis rests on.
4. **No judges, no human-κ.** 3C3H was not run, and the 50-item native-speaker validation does not
   exist. Prime directive 5 blocks every judge-based claim until it does.
5. **Fertility table incomplete.** `meta-llama/Llama-3.2-3B-Instruct` is manually gated, so the
   tokenizer comparison can ship at most 4 of 5 tokenizers.
6. **Sovereign posture unverified on a cluster.** The charts, NetworkPolicies and egress-zero alert
   are authored but no k3s/k3d run has exercised them (no Docker/sudo available), so the "24 h
   egress-zero" criterion is unmet.
7. **`cost_usd` in MLflow reads 0.4396**, an artifact of the `$0.60/h` default multiplied by
   0.733 h. The true figure is **$0** (local compute). Prefer this document over that field.
8. **The served model emits stray `<tool_call>` tokens** (§4, demo). Until that is understood the
   GGUF is a demonstrable artifact, not a deployable one.
9. **Domain answers are unvalidated and at least one is wrong** (USD quoted for an AED product).
   No factual accuracy claim is available, which is the same gap as items 3 and 4 seen from the
   output side rather than the eval side.

---

## 7. Engineering notes from the run

`train/sft.py` and the P3 scripts had never executed end-to-end before this run. Seven defects
surfaced, every one invisible to ruff, mypy and the unit suite, and every one reachable only with
a warm GPU:

| # | Defect | Fix |
|---|---|---|
| 1 | `trl>=1.0` unsatisfiable with Unsloth → uv silently resolved a year-old Unsloth that cannot import | ADR-0006; `unsloth>=2026.7` floor + preflight now *imports* the stack |
| 2 | `target_modules: all-linear` iterated into characters by Unsloth's text path | `resolve_target_modules()` + torch-free tests |
| 3 | Unsloth imported *after* trl, so a patched model ran through stock TRL | ADR-0007; AST test asserts import order |
| 4 | `formatting_func` assumed batched input | shape detection |
| 5 | …then returned a bare string for the single-example probe | always returns `list[str]`; test asserts the invariant |
| 6 | AWQ OOM — llm-compressor only auto-offloads for MoE, and Qwen3-4B is dense | `offload_device: cpu` in the recipe |
| 7 | `gguf.sh` never built `llama-perplexity`, so the release gate could not run | added to the cmake targets |
| 8 | GGUF gate compared across runtimes, one-sided | matched baseline + two-sided threshold |
| 9 | `edge-bench.sh` looked for the GGUF at a compose mount path, and required Docker — which the CPU-only edge target does not have | prefers `ml/out/`, and a native `llama-bench` before falling back to Docker |
| 10 | Transfer verification reported 6 dotfiles missing: `lstrip("./")` strips leading dots as a character set, so `./.gitignore` became `gitignore` | `removeprefix("./")` |

Number 10 was in the verification tooling rather than the pipeline, and it is the one worth
remembering: it made a *complete* 22.41 GB transfer look like a failed one. Because the erase step
was gated on verification rather than run alongside it, the outcome was a refusal to delete rather
than the loss of 8,223 files. Ordering the guard before the irreversible action is what turned a
bug into an inconvenience.

Preflight now imports the training stack for real rather than calling `find_spec`, which is what
let a broken dependency graph report "15 passed, 0 blocking" one second before an ImportError.

### P4 added two more of the same kind (2026-07-29)

| # | Defect | Fix |
|---|---|---|
| 11 | `max_model_len` never passed to vLLM. Qwen3-4B advertises a 262,144-token context, so vLLM sized KV cache to 36 GiB against the 11.45 GiB free after weights and the engine core refused to start — identically for both models, 12 minutes into a run that then wrote `p4 done` over two **empty** report dirs | `max_model_len=8192` pinned in `run_lm_eval.sh` and stamped into `PROVENANCE.yaml` |
| 12 | `ninja` unreachable. The harness called `$EVAL_VENV/bin/lm_eval` by absolute path, which leaves `$EVAL_VENV/bin` off `PATH`; vLLM's inductor backend shells out to `ninja` by bare name and died with `FileNotFoundError` while ninja sat installed in that very venv | `export PATH="$EVAL_VENV/bin:$PATH"`; `ninja` now named explicitly in the venv install |

Number 12 is the transferable one: **absolute-path invocation of a venv binary is not equivalent to
activation.** The interpreter and libraries resolve correctly, so it looks equivalent right up to the
moment a dependency shells out to a sibling console script by bare name.

Both were masked by our own logging. The wrapper piped each eval through `tail -40`, which preserved
the re-raise and discarded the `ValueError` explaining it — the log read
"Engine core initialization failed. See root cause above" with the root cause cut off. Diagnosing it
cost a fresh GPU repro the next morning. The wrapper now writes a full per-model log and summarises
into the run log. **Never pipe a GPU run's output through `tail`** — truncation that keeps the
exception and drops the cause is worse than no logging, because it looks like logging.

A third, smaller lesson from the same session: the polling watcher used
`grep -c pattern file || echo 0`, which emits **two** zeros on no-match (grep exits 1), so a
string comparison against `"0"` read as "finished" and reported completion twice while the run was
healthy and mid-flight. Parse integers, not blobs.
