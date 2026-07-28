# SANAD — measured results, run of 2026-07-26 → 28

Every number here traces to a file produced by the pipeline (prime directive 6). Figures that were
not measured are written `—`, never estimated (§8.2). Read the [Limits](#limits--what-this-run-does-not-show)
section before quoting anything.

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

Training metrics (loss curve, peak VRAM, FLOPs) come from MLflow run `b8ccaafc`
(`hilarious-shad-242`), preserved in `mlflow.db` in the artifact archive. **Model weights are not
in git** (prime directive 6) — the archive lives at `~/sanad-artifacts/` with all 8,223 files
sha256-verified against the machine that produced them.

---

## 1. Provenance and honesty summary

This matters more than the metrics, so it goes first.

| Claim | Available? | Why |
|---|---|---|
| Reproducible QLoRA recipe on one 24 GB GPU | **yes** | full config + lockfiles + pinned base revision; peak VRAM measured |
| Quantization preserves Arabic | **yes, for AWQ** | ΔPPL per language on a fixed held-out shard |
| CPU-only edge deployment works | **yes** | GGUF Q4_K_M runs under llama.cpp at the pinned commit |
| "Matches a 5–10× larger model in-domain" | **NO** | domain eval holds 12 of 300 items; no comparator was run |
| Any benchmark score (ArabicMMLU, AraTrust, …) | **NO** | P4 never executed |
| Any judge-based (3C3H) claim | **NO** | no judges run, and no human-κ sample exists |

**The training corpus is 13.5% machine-drafted with no human reviewer.** Those records carry
`provenance: synthetic` honestly, but it means the domain adaptation is trained on text no
native speaker has validated. That alone blocks the headline claim, independent of P4.

---

## 2. Data (P1) — `ml/data/MANIFEST.yaml`

| | records | provenance | licence |
|---|---|---|---|
| CIDAR (`arbml/CIDAR`) | 9,962 | native | Apache-2.0 |
| sanad-bank-pairs (own) | 1,277 | **synthetic** | CC-BY-4.0 |
| **total** | **12,007** | | `profile: commercial` gate ✅ |

Provenance split: **native 86.52% · translated 0% · synthetic 13.48%**
Language split: **ar 90.39% · en 5.86% · mixed 3.75%**

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

### AWQ quality gate — PASSED · `evals/reports/ppl_gate_awq-w4a16.json`

Perplexity on the fixed 256-item bilingual holdout, quantized vs bf16, both via transformers.

| subset | bf16 | AWQ W4A16 | ΔPPL | gate ≤ 3% |
|---|---|---|---|---|
| pooled | 6.871 | 6.972 | **+1.48%** | ✅ |
| **Arabic** (n=226) | 6.736 | 6.833 | **+1.44%** | ✅ |
| English (n=20) | 11.308 | 11.577 | +2.39% | ✅ |

**Arabic degraded less than English.** That is the point of requiring ≥40% Arabic in the
calibration set — §5.3 calls English-only calibration the most common silent failure mode, and
this is direct evidence the bilingual calibration worked. Note the English subset is only 20
records and therefore noisy; do not read the AR-vs-EN gap itself as meaningful.

### GGUF Q4_K_M quality gate — PASSED · `evals/reports/ppl_gate_sanad-Q4_K_M.gguf.json`

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
is the 3.75% of the corpus that is hardest to get right.

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

## 5. Limits — what this run does **not** show

1. **No benchmark numbers.** P4 (lm-eval over ArabicMMLU / AraTrust / MadinahQA / ALRAGE) was not
   run; the GPU was returned to its shared owners instead. The regression gate
   (domain ≥ base +5 pts, ArabicMMLU ≥ base −1 pt) has therefore never been evaluated.
2. **No comparator.** ALLaM-7B, jais-6.7b and a large generalist were never measured, so no
   relative claim exists. Falcon-H1 has no exact repo id pinned in §15 and was dropped rather
   than guessed.
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

## 6. Engineering notes from the run

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
