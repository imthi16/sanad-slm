# Model Card — {{model_name}} {{version}}

> Generated per release by `registry/push.py` guidance; every number below must trace to a
> report in `ml/evals/reports/` by hash (working agreement #6). No frontier-beating claims.

## Summary

| | |
|---|---|
| Base model | {{base_model}} @ `{{base_revision}}` (Apache-2.0) |
| Method | QLoRA (NF4) + DoRA, r=16 α=16, Unsloth + TRL, non-thinking chat template |
| Data | {{n_records}} records — provenance: {{native_pct}}% native / {{translated_pct}}% translated / {{synthetic_pct}}% synthetic (MANIFEST sha `{{data_sha}}`) |
| Train budget | {{train_hours}} h on 1×24 GB GPU · peak VRAM {{peak_vram}} GB · ${{cost_usd}} |
| Artifacts | merged-bf16 · AWQ-W4A16 (compressed-tensors) · GGUF Q4_K_M (+bilingual imatrix) |
| License | Apache-2.0 (weights derivative of Apache-2.0 base; data CC-BY-4.0/Apache-2.0 only) |
| Signature | cosign `{{cosign_ref}}` · artifact sha256 `{{artifact_sha}}` |

## Intended use & scope

UAE banking/compliance assistant (MSA Arabic + English + light code-switching). **Not** a
general-purpose model; **no dialect coverage in v1**; not a substitute for compliance review.

## Evaluation (re-measured locally, lm-eval @ `{{lm_eval_rev}}`)

| Benchmark | Base | This model | ALLaM-7B | jais-6.7b | Falcon-H1-7B* |
|---|---|---|---|---|---|
| ArabicMMLU | {{…}} | {{…}} | {{…}} | {{…}} | {{…}} |
| AraTrust | {{…}} | {{…}} | {{…}} | {{…}} | {{…}} |
| Domain (sanad_bank_eval_v1) | {{…}} | {{…}} | {{…}} | {{…}} | {{…}} |

\* Falcon-H1 = benchmark comparator only (Falcon-LLM License — not in the shipping path).

3C3H (sovereign judges: Falcon-H1-7B + ALLaM-7B): final {{judge_final}}/5, correctness gate
{{correct_rate}}%, **human↔judge κ = {{human_kappa}} (n=50)** — judge claims are invalid
without this number. Krippendorff α = {{alpha}}.

## Quantization gates

ΔPPL AWQ {{awq_dppl}}% (≤3) · GGUF {{gguf_dppl}}% (≤5) · ArabicMMLU drop {{mmlu_drop}} pt (≤1.0).
Calibration: bilingual, ≥40% Arabic (English-only calibration measurably degrades Arabic).

## Efficiency

{{ttft}} ms TTFT · {{tps_gpu}} tok/s (vLLM AWQ, batch {{batch}}) · {{tps_edge}} tok/s @
{{watts}} W (Orin Nano, {{power_mode}}, JetPack {{jetpack}}) · ${{usd_per_1m}}/1M output
tokens (model: `evals/reports/cost_model.md`).

## Limitations & risks

- Arabic tokenizer fertility of the base ({{fertility}} tokens/word on MSA) bounds effective
  context and edge latency — see the fertility report.
- Judged wins are in-domain only; out-of-domain behavior reverts toward the base model.
- PII scrubbing applies to logs, not to model outputs; deploy behind the API gateway.
