# ADR-0003: Zero-cost portfolio track — free substitutes for every paid component

Date: 2026-07-08 · Status: accepted · Items 1, 2 and 4 amended by ADR-0004 (local RTX 4090
workstation is the primary compute; Jetson hardware target removed entirely)

## Context

SANAD is a portfolio project. The original plan already capped training at < $50, but several
components still assumed spending money: a cloud GPU burst (AWS me-central-1), a physical
Jetson Orin, a rented 72B comparator endpoint, a self-hosted GPU CI runner, and on-prem k3s
nodes. The owner wants the entire project executable at **$0** using only free resources,
without weakening the honesty directives (§0.5) or changing the architecture contracts
(§2–§9). IaC and edge artifacts remain in the repo as reviewable engineering work — they are
demonstration artifacts, validated in CI (`tofu validate`, `helm lint`, `ansible-lint`) but
never applied against paid infrastructure.

## Decisions

1. **Training GPU → Kaggle (primary) / Google Colab free tier (fallback).** Kaggle gives
   ~30 GPU-hours/week (2×T4 or P100); QLoRA NF4 of Qwen3-4B needs ~8 GB — fits a single T4.
   Caveat: T4/P100 have no bf16 — P2 adds a `qwen3-4b-qlora-dora-t4.yaml` variant
   (`bf16: false, fp16: true`, otherwise identical) and the report states which config ran.
   The `gpu_train` Terraform module stays as a portfolio artifact (plan/validate only).
   Data-residency framing changes from "training data never leaves UAE region" to "all
   training data is public or own-authored — no residency constraint applies".
2. **Jetson Orin edge → `edge-sim` compose profile (x86 llama.cpp), already in the repo.**
   Efficiency-panel numbers are labeled `platform: x86-sim` and are **never** presented as
   Jetson numbers (prime directive 5). The Ansible role and jetson-bench runbook stay as
   artifacts; if a physical board is ever borrowed, the real numbers slot in unchanged.
3. **Large-model comparator → free-tier hosted APIs, dev mode only.** The headline
   "small-matches-large" comparison uses whatever large open model is reachable through a
   free tier (e.g. OpenRouter free models, Groq free tier, Google AI Studio) — scores stored
   with `sovereign=false` as already specified. If no free endpoint offers a suitable large
   model at eval time, the claim is scoped down to the models we can run ourselves
   (Falcon-H1-7B, ALLaM-7B) — an honest narrower claim beats an unfunded broad one.
4. **Sovereign judges → quantized judges on Kaggle sessions.** Falcon-H1-7B + ALLaM-7B run
   AWQ/GGUF-quantized on free Kaggle GPUs; judge outputs are ingested via the existing
   `POST /v1/eval/runs/{id}/ingest`. Human validation (50 items) is done by the owner +
   one native-speaker volunteer — already free.
5. **k3s cluster → k3d (k3s-in-docker) on the dev machine.** Helm charts, sovereign-guard
   NetworkPolicies, and the egress-zero alert are demonstrated on a local k3d cluster; the
   `k3s_cluster` module stays plan-only. The air-gapped demo remains
   `compose.sovereign.yml` with Wi-Fi off (already the P5 acceptance).
6. **Registry → MinIO locally + Hugging Face Hub for public artifacts.** Released
   adapters/GGUFs are mirrored to a free HF repo (also portfolio visibility). Image signing
   uses cosign **keyless** with GitHub OIDC (free, no KMS).
7. **CI → GitHub Actions free tier (repo must be/stay public).** The self-hosted GPU runner
   is dropped: `eval.yml` becomes `workflow_dispatch` that ingests eval-report artifacts
   produced by Kaggle notebook runs, then applies the same regression gate. Trivy, Syft,
   cosign, Playwright all run fine on free runners.
8. **Live demo hosting → screen recordings + local demos; optional HF Spaces.** The 3D
   dashboard with frozen report JSON can also be exported as a static build to GitHub Pages
   (free) — clearly labeled as replaying real, hash-traceable reports rather than live
   inference.

## Consequences

- Budget line in reports changes from "< $50" to "**$0** (free-tier compute: Kaggle/Colab)".
- Every claim keeps its provenance: sim numbers labeled sim, free-API judge scores labeled
  `sovereign=false`, replayed dashboards labeled replayed.
- Weekly Kaggle GPU quota (~30 h) becomes the real scheduling constraint for P2–P4; runs
  must be checkpointed (Unsloth resume) to survive session limits (9 h/session).
- Terraform/Ansible/Helm remain interview-discussable artifacts with CI validation but no
  cloud spend; nothing in §2–§9 contracts changes.
