# Paper draft — ArabicNLP/OSACT workshop (P7)

**Working title:** *Sanad: A Reproducible Recipe for Sovereign Bilingual Banking SLMs —
QLoRA Fine-tuning, Bilingual-Calibrated Quantization, and Multi-Judge Arabic Evaluation on
a $50 Budget*

**Scope guard (per CLAUDE.md P7):** reproducible recipe + eval harness + fertility/edge
measurements. **No frontier-beating claims.** Every number cites a report hash.

## Outline

1. **Introduction** — sovereignty as a deployment constraint (zero-egress), not a slogan;
   the in-domain small-vs-large question for Gulf banking Arabic.
2. **Related work** — Arabic-native SLMs (ALLaM, jais family, Falcon-H1-Arabic); OALL-v2 /
   AraGen / 3C3H evaluation; QLoRA/DoRA; AWQ + GGUF quantization for Arabic.
3. **Data** — CIDAR core + own banking pairs; provenance taxonomy (native/translated/
   synthetic) as a first-class reported statistic; contamination hygiene for the frozen
   300-item domain set.
4. **Recipe** — Unsloth QLoRA+DoRA on Qwen3-4B (non-thinking); exact configs; <16 GB VRAM /
   <$50 acceptance; merge → AWQ-W4A16 and GGUF Q4_K_M with **bilingual** calibration/imatrix;
   the ppl-gate (per-language ΔPPL, not pooled).
5. **Evaluation harness** — pinned lm-eval tasks; domain eval design; 3C3H with a
   family-exclusion judge pool; disagreement tracking (Krippendorff α, pairwise κ, heatmap);
   50-item human validation with human↔judge κ as a publication gate.
6. **Results** — benchmark matrix (all re-measured); in-domain delta vs base and vs one
   large generalist; forgetting check (ArabicMMLU drift ≤1 pt).
7. **Fertility & edge economics** — tokens/word across five tokenizers on three fixed
   corpora; measured CPU-edge (x86-local) tok/s + watts; $/1M tokens from the published cost model.
8. **Limitations** — MSA-only (no dialects), single domain, judge-pool size, raster-level
   contamination risk in public benchmarks.
9. **Reproducibility statement** — seeds, pinned revs (harness commit, base model sha,
   llama.cpp commit), MANIFEST/report hashes, Apache-2.0 release.

## Artifact checklist (camera-ready)

- [ ] configs + MANIFEST hashes table
- [ ] eval reports archived + hashed
- [ ] model card + cosign-signed artifacts on the registry
- [ ] human validation protocol + anonymized scores
