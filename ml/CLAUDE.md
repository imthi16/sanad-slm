# CLAUDE.md — `ml/` · ML pipeline specification

> Loads when Claude works under `ml/`. The root [`CLAUDE.md`](../CLAUDE.md) holds the prime
> directives, the mode matrix and the current phase state — read it first; it wins on conflict.

## 5.1 Data layer

**Record schema** — every SFT/eval record validates against `ml/data/schemas/record.schema.json`.
The fields the gates key on: `lang` (`ar | en | mixed`), `provenance`
(`native | translated | synthetic`), `source.license`, `pii_checked`, `split`.

**Sources & handling**

| Dataset | Role | License | Handling |
|---|---|---|---|
| CIDAR (arbml, 10k) | native instruction core | Apache-2.0 | `ingest_cidar.py`; keep `provenance=native` |
| Own banking/compliance pairs (target 800–1,500; 60% AR / 30% EN / 10% code-switch) | domain SFT | CC-BY-4.0 (ours) | `curate_bank.py` template: question, grounded answer, source citation field, reviewer initials |
| ArabLegalEval | domain eval inspiration + methodology | check per-file | eval-only |
| AraFinNews (212.5k pairs) | research-only adaptation experiments | **non-commercial** | `data/quarantine/` — CI blocks it from any `profile: commercial` manifest |
| ArabicMMLU / AraTrust / MadinahQA / ALRAGE | benchmarks | per-benchmark | eval-only, fetched by harness |

**Pipeline order (all idempotent, all log to MLflow):** ingest → `normalize.py` (Unicode NFC;
CAMeL normalization used **only** for dedup/lang-id keys, raw text preserved for SFT) →
`langid.py` (fasttext lid.176; tag `mixed` when both scripts > 15%) → `dedup.py` (MinHash,
Jaccard ≥ 0.85 drop) → schema validation → `split.py` → `calib.py` → `MANIFEST.yaml` regeneration.

`split.py` writes `data/processed/splits/{train,val}.jsonl` — the two shards `sft.py` loads as
`dataset` and `eval_holdout`. Seeded (3407) and stratified by `(lang, provenance)`, so the same
corpus always yields the same split and val mirrors train per language; an unstratified sample of a
60/30/10 corpus can under-represent code-switching enough that held-out loss says nothing about the
case that matters most. They live in a **subdirectory** because every other stage globs
`data/processed/*.jsonl` non-recursively — keeping them out of that glob stops them being
re-normalised on a second run and double-counted in the manifest.

`calib.py` then builds the three artifacts P3 consumes and nothing previously produced:
`calib_bilingual_512.jsonl` (AWQ), `calib_bilingual.txt` (llama.cpp imatrix) and
`ppl_heldout_bilingual.jsonl` (the ppl gate's fixed shard). **Calibration is drawn from train and
the PPL holdout from val**, so the gate never scores perplexity on data the quantizer was
calibrated on — a gate that did could not detect the regression it exists to catch. The Arabic
target is measured in **characters, not records**, because that is what `awq.py` gates on: half the
records Arabic still misses the 40% floor when the English records are longer. Sample count and the
floor are read from `configs/quant/awq-w4a16.yaml` so the generator cannot drift from its gate.

**`MANIFEST.yaml` is a CI gate:** aggregates per-source counts, license, provenance split
(native/translated/synthetic %), sha256 of the processed shards, and a `profile:` field.
`just data-gate` fails if any record's license ∉ {Apache-2.0, CC-BY-4.0, MIT} while
`profile: commercial`. The native-vs-translated split is printed into every eval report (rigor
signal — see research doc §2).

## 5.2 Fine-tuning (Unsloth QLoRA + DoRA)

Canonical config — `ml/configs/train/qwen3-4b-qlora-dora.yaml`; `train/sft.py` consumes it, and any
hyperparameter change = **a new file, never a mutation of this one**. The load-bearing values (do
not drift them casually): `seed: 3407`, `max_seq_len: 4096`, `load_in_4bit` NF4, DoRA on
(`use_dora: true`, `target_modules: all-linear`, r=alpha=16), effective batch 16 (4 × grad_accum 4),
bf16, `adamw_8bit`, `chat_template: qwen3` trained in **non-thinking** mode
(`enable_thinking=false` — we ship the low-latency path).

`train/sft.py` responsibilities: load config → Unsloth `FastLanguageModel` → apply Qwen3 chat
template with `enable_thinking=False` (we ship the low-latency non-thinking mode) → TRL
`SFTTrainer` → log loss/LR/VRAM to MLflow → save adapter **and** merged bf16 →
`registry/manifest.py` writes lineage. Acceptance: run completes on the local RTX 4090 with
< 16 GB peak VRAM; val loss curve monotone-ish; total compute cost logged ($0 — local
workstation, ADR-0004; if a run overflows to Kaggle/Colab T4, use an fp16 config variant).

**Comparator matrix** (evaluated, never retrained): ALLaM-7B-Instruct-preview, jais-family-6.7b-chat
(Apache-2.0, Arabic-native), Falcon-H1-Arabic-3B/7B (SOTA reference), and one large generalist
(e.g., Qwen2.5-72B-Instruct via a free-tier hosted API — ADR-0003, **dev mode only**) for the headline
"small-matches-large in-domain" claim.

## 5.3 Quantization

Two release artifacts per model version; both must pass `ppl_gate.py`:

```bash
# (a) AWQ W4A16 for vLLM — llm-compressor (AutoAWQ is archived; do not add it)
uv run python quantize/awq.py --model out/merged-bf16 \
  --recipe configs/quant/awq-w4a16.yaml \
  --calib data/processed/calib_bilingual_512.jsonl   # ≥40% Arabic — English-only calib degrades AR

# (b) GGUF Q4_K_M for llama.cpp CPU edge — with importance matrix on bilingual text
python llama.cpp/convert_hf_to_gguf.py out/merged-bf16 --outfile out/sanad-f16.gguf
./llama-imatrix -m out/sanad-f16.gguf -f data/processed/calib_bilingual.txt -o out/imatrix.dat
./llama-quantize --imatrix out/imatrix.dat out/sanad-f16.gguf out/sanad-Q4_K_M.gguf Q4_K_M
```

**Quality gate (`ppl_gate.py`):** perplexity on a fixed bilingual held-out shard, quantized vs
bf16 — fail release if ΔPPL > 3% (AWQ) or > 5% (Q4_K_M), or if ArabicMMLU drops > 1.0 pt.
Rationale: the single most common silent failure is English-calibrated quantization quietly
wrecking Arabic.

## 5.4 Evaluation harness (the credibility core)

**(a) Standardized benchmarks — lm-evaluation-harness, pinned:**

```bash
# ml/evals/harness/run_lm_eval.sh  (REV pinned; bump only via PR + rerun of all models)
LM_EVAL_REV=<pinned-commit>
uv run lm_eval --model vllm --model_args pretrained=$MODEL,dtype=bfloat16 \
  --tasks arabicmmlu,aratrust,madinahqa,alrage --num_fewshot 0 --batch_size auto \
  --log_samples --output_path evals/reports/$RUN_ID
```

Run the identical command for: base Qwen3-4B, fine-tuned, ALLaM-7B, jais-6.7b, Falcon-H1-3B/7B.
Vendor-reported numbers are quoted only next to our re-measured ones.

**(b) Domain eval — `sanad_bank_eval_v1.jsonl`:** 300 own-authored held-out items (150 AR /
120 EN / 30 code-switch): extraction (exact-match/F1), classification (accuracy/macro-F1),
grounded QA (judged). sha256 committed; never enters training; treat as private (contamination
hygiene, BALSAM-style).

**(c) 3C3H multi-judge harness (`evals/judge/`):**
- **Rubric:** Correctness is a binary gate; if fail → score 0. Else Completeness, Conciseness,
  Helpfulness, Honesty, Harmlessness each 1–5; final = mean of the five, reported per-dimension.
  Rubrics exist in AR and EN (`rubric_ar.md`, `rubric_en.md`); judge sees the item's language.
- **Judge pool rule:** never a judge from the *tested model's family* (self-preference bias). For
  Qwen3-4B under test → sovereign judges = **Falcon-H1-7B-Instruct + ALLaM-7B-Instruct**, served
  locally via vLLM. `dev` mode may add one frontier API judge for calibration; its scores are
  stored with `sovereign=false` and excluded from headline numbers.
- **Disagreement tracking (`agreement.py`):** Krippendorff's α overall + per-dimension, pairwise
  judge Cohen's κ, and a disagreement heatmap (judge × dimension) exported as JSON for the
  dashboard. Items with per-item judge spread ≥ 2 points → routed to the human queue.
- **Human validation:** 50-item stratified sample scored by a native Arabic speaker
  (`human_validation.md` protocol); report human↔judge κ. **No judge-based claim ships without
  this number** (prime directive 5).

**(d) Tokenizer fertility (`fertility/measure.py`):** run `just sync-tokenizers` first — it
fetches the five `tokenizer.json` files (**tokenizers only, never weights**) into
`out/tokenizers/<org>__<model>/`, the layout `measure.py` and the API's `tokenizers_dir` both
expect, and records the resolved revision sha per tokenizer in `tokenizers.manifest.json` so a
published tokens/word figure is tied to a tokenizer version. **That manifest lives under `ml/out/`
and is therefore gitignored** — anything published must carry the revisions with it rather than
pointing at it, which is why `measure_specimen.py` copies them into the demo payload it commits.
Sovereign mode cannot sync (no hub) —
populate the directory while online and copy it to the air-gapped host. tokens/word for {Qwen3, jais-family, ALLaM,
Falcon-H1, Llama-3.2} tokenizers over three fixed corpora (MSA news 10k words, banking-domain 5k,
English 10k). Outputs `fertility.json` → consumed by the API and the 3D hero. This is the
project's signature insight: fertility ≈ latency ≈ cost ≈ effective context for Arabic.

**(e) Efficiency panel:** TTFT, tok/s (prompt+gen), peak VRAM/RSS, watts (CPU edge via RAPL;
GPU via DCGM), $/1M output tokens (electricity+amortization model in `evals/reports/cost_model.md`).

## 5.5 Model registry & release

`registry/push.py` uploads to MinIO:

```
s3://sanad-models/sanad-qwen3-4b-bank/{version}/
  adapter/ · merged-bf16/ · awq-w4a16/ · gguf/sanad-Q4_K_M.gguf
  manifest.json     # base+revision, data MANIFEST sha, train-config sha, eval-report sha,
                    # licenses[], created_by, cosign signature ref
  MODEL_CARD.md     # generated from docs/model-cards/template.md
```

A model version is **releasable** only when: license gate ✓, ppl gate ✓, eval report attached ✓,
manifest signed (cosign) ✓. The API's `/v1/registry` reads these manifests directly.

## Dependency ceilings

The pins in this workspace interlock — Unsloth's release windows cap TRL, transformers, datasets and
torch, which in turn cap `llmcompressor`, and the `train`/`quant` extras share one venv. **Raise any
of them only together, and re-run `just preflight`.** The full ceiling matrix and the ADR-0006
rationale are in root [`CLAUDE.md`](../CLAUDE.md) §3.1 — read it before bumping anything.
