# CLAUDE.md — SANAD (سَنَد) · Sovereign Bilingual SLM Platform

> **Sanad** (Arabic: *support, backing; a debt instrument in Gulf banking*) — a sovereign,
> air-gapped, bilingual (Arabic/English) small-language-model platform: QLoRA fine-tuning →
> quantization → reproducible bilingual evaluation → on-prem/edge serving → 3D web dashboard.
>
> **Owner:** Mohamed · **Target:** UAE sovereign-AI employers (Core42/Presight/TII/MBZUAI, Emirates NBD)
> + ArabicNLP/OSACT workshop paper · **Repo license:** Apache-2.0 (code), CC-BY-4.0 (own datasets/docs)

This file is the single source of truth for Claude Code and human contributors. Read it fully
before writing code. When this file and a README disagree, this file wins. Update it via PR when
architecture decisions change (and add an ADR in `docs/adr/`).

Per-area detail lives in directory-scoped files that load only when you work there — see
[§2](#2-where-the-rest-of-this-spec-lives).

> **⚠️ Current repository state (as of 2026-07-29): the pipeline has RUN end to end. P0–P2 done;
> P3–P5 and P7 partial; P6 not started.** `just check` is green (ruff+mypy+pytest both Python
> workspaces, biome+tsc+vitest+i18n-sync web, data-gate, verify-no-cdn) and all 23 Playwright
> tests pass (RTL+LTR for 6 routes, design-token assertions, grapheme-safe streaming).
> Every measured figure is traced by hash in **[`RESULTS.md`](./RESULTS.md)** — read it before
> quoting any number. That includes the training run: MLflow's store is not in git, so
> `just export-metrics` writes a deterministic, hashed export of it (`train_metrics_b8ccaafc.json`)
> and the VRAM/wall-time/loss figures are read from there, not from an untracked database.
>
> **What exists:** 11,239 data records (CIDAR 9,962 native + 1,277 own bank pairs, gate green) ·
> a fine-tuned model (44 min, peak VRAM **15.59 GB**, **$0**) · AWQ + GGUF artifacts, both
> ΔPPL-gated per language · ArabicMMLU on fine-tuned **59.33**, base **59.79** (−0.46 pt, forgetting
> gate ✅), AWQ **57.58**, ALLaM-7B comparator **70.01** · chat verified end to end on CPU-only
> llama.cpp through the real serving path.
>
> **What does not (and must not be claimed):** **AWQ is withheld** — it lost 1.75 pt of ArabicMMLU,
> failing §5.3's accuracy clause, so the shipping path is **bf16 + GGUF Q4_K_M** · the **domain eval
> still holds 12 of 300 items**, so the "matches a 5–10× larger model" thesis has *no* supporting
> evidence · **no judges have run and no human-κ sample exists**, so every 3C3H claim is invalid
> under prime directive 5 · **`just fertility` cannot run** — the three frozen corpora in
> `evals/fertility/corpora/` were never collected, so there is **no corpus-level fertility result**;
> the Specimen hero measures a *single sentence* live through 3 of 5 tokenizers
> (`just sync-tokenizers`, `just capture-specimen`), which is a demonstration of the mechanism and
> not the §5.4d benchmark · the own bank pairs are `provenance: synthetic` and unreviewed.
>
> **Next: P4** — take the domain eval to 300 items, then judges + the 50-item human validation.
> Nothing downstream (regression gate, headline table, paper claims) is unblocked until that lands.
> Pins are filled and verified (§15); the `.sops.yaml` age recipient is set. Two gated repos still
> need a human to accept terms once, and both silently shrink the evidence base:
> **`meta-llama/Llama-3.2-3B-Instruct`** (`gated: manual`, one of the five fertility tokenizers —
> 3 of 5 are synced) and **`inceptionai/jais-family-6p7b-chat`** (`gated: auto`, why the jais
> comparator is absent). Update this notice whenever a phase changes state.

---

## 0. Mission, prime directives, non-goals

**Mission.** Prove — with a shipped, measured artifact — that a ~4B bilingual SLM, fine-tuned for
< $50 on a single 24 GB GPU, can **match a 5–10× larger general model on a narrow UAE
banking/compliance domain** while running fully air-gapped on a sovereign GPU node (vLLM + AWQ)
and on commodity CPU-only hardware at the edge (llama.cpp + GGUF), with a reproducible Arabic/English
evaluation harness (OALL-v2 native tasks + 3C3H multi-judge with disagreement tracking).

### Prime directives (never violate)

1. **Sovereignty is a build mode, not a slogan.** In `SANAD_MODE=sovereign`, zero network egress:
   `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, no CDN assets, no external fonts/analytics,
   local-only judges, default-deny K8s NetworkPolicy. CI has an "egress = 0 bytes" alert test.
2. **Licensing guardrails.** Shipping path (train → merge → quantize → serve) may only touch
   Apache-2.0 assets: **Qwen3-4B (primary), ALLaM-7B-Instruct-preview, jais-family-6.7b, CIDAR**.
   `Falcon-H1-Arabic-*` (Falcon-LLM License) = benchmark comparator only. **Fanar / jais-adapted /
   AraFinNews = research-quarantine** (`ml/data/quarantine/`, never in the commercial train
   manifest — CI license gate enforces this).
3. **Arabic is a first-class citizen.** RTL everywhere (logical CSS properties only), bilingual UI
   strings kept in sync, Arabic-aware tokenizer metrics (fertility) surfaced as a product feature,
   dataset records carry `provenance: native | translated | synthetic` and the split is always
   reported. Never machine-translate eval sets and call them native.
4. **Reproducibility over vibes.** Pinned lockfiles (`uv.lock`, `pnpm-lock.yaml`), pinned
   lm-eval-harness commit, fixed seeds, dataset `MANIFEST.yaml` with sha256, every model artifact
   ships `manifest.json` (lineage: base → data hash → train config hash → eval report hash).
5. **Honest claims only.** "Matches a 72B model" is claimed **only** on the in-domain eval, with
   the efficiency delta reported alongside. Judge-based wins require the human-validated sample.
   Vendor benchmark numbers are re-measured locally before being quoted.
6. **Small PRs, conventional commits, `just check` green before "done".** Never commit weights,
   raw datasets, or secrets (SOPS-encrypted files only).

### Non-goals

- No pretraining / continual pretraining at scale; no general-purpose frontier claims.
- No dialect coverage in v1 (MSA + English + light code-switching only; dialects = P2).
- No multi-tenant SaaS auth (single-team demo auth is enough); no mobile app.
- No Kubernetes operator authoring — plain Helm charts on k3s are the ceiling.

### Zero-cost portfolio track (ADR-0003 + ADR-0004 — active)

This is a portfolio project; the whole plan executes at **$0** on the owner's workstation
(i9-14900K 24C/32T + RTX 4090 24 GB — exactly the "single 24 GB GPU" the recipe targets).
Read paid-infra mentions through ADR-0003/0004: **training runs locally on the RTX 4090**
(bf16 native; Kaggle/Colab free tier is overflow fallback only); the **edge target is
CPU-only llama.cpp on the same box** (compose `edge` profile; numbers labeled `x86-local`;
the Jetson hardware target was removed by ADR-0004); large-model comparator via **free-tier
hosted APIs** (dev mode, `sovereign=false`) or the claim is honestly narrowed; judges served
quantized on the 4090; k3s demos on **k3d** locally; public artifacts mirrored to
**Hugging Face Hub**; CI on GitHub Actions free tier with `eval.yml` as `workflow_dispatch`
ingesting locally produced reports (no self-hosted GPU runner). Terraform/Helm stay in-repo
as CI-validated artifacts (`tofu validate`, lint) but are never applied against paid
infrastructure. Budget lines in reports read "$0 (local compute)".

---

## 1. System architecture

```
                 ┌────────────────────────  TRAIN (local RTX 4090 workstation — ADR-0004)
                 │  uv env ──▶ Unsloth QLoRA+DoRA (Qwen3-4B)   [gpu_train TF module: plan-only artifact]
                 │        │                                    │
                 │        ▼                                    ▼
                 │  MLflow (self-hosted)                merge bf16 ─▶ llm-compressor AWQ-W4A16
                 │                                             └────▶ llama.cpp GGUF Q4_K_M (+imatrix)
                 ▼
        ┌── MinIO model registry (s3://sanad-models/…, manifest.json, sha256, cosign) ──┐
        │                                                                               │
   SOVEREIGN SERVER (k3s, on-prem)                                        EDGE (CPU-only x86 box)
   vLLM (AWQ, OpenAI-compatible) ◀──┐                                  llama-server (GGUF Q4_K_M)
        │                           │ ModelRouter                               │  /metrics + RAPL
        ▼                           │                                           ▼
   sanad-api (FastAPI, SSE) ────────┴──────────── Postgres 17 · Redis · Langfuse(optional)
        │            ▲
        ▼            │ OpenAPI → generated TS client
   sanad-web (React 19 + R3F 3D dashboard, nginx, CSP self-only)
        │
   Observability: kube-prometheus-stack · dcgm-exporter · Grafana · Loki · egress-zero alert
```

Three runtime **modes** select behavior everywhere (config, compose profiles, Helm values):

| Mode | Where | Network | Inference upstream | Judges |
|---|---|---|---|---|
| `dev` | laptop / cloud GPU | online allowed | vLLM or llama.cpp local | local + optional API judge (calibration only, flagged) |
| `sovereign` | k3s on-prem | **zero egress** | vLLM (AWQ) | local only (Falcon-H1-7B + ALLaM-7B) |
| `edge` | CPU-only x86 box | zero egress | llama.cpp (GGUF) | n/a (telemetry only) |

---

## 2. Where the rest of this spec lives

The layout is what `ls` tells you; these are the files that carry the *rules* for each area. Each
loads only when Claude works under its directory, so this root file stays cheap to always load:

| File | Covers |
|---|---|
| [`ml/CLAUDE.md`](./ml/CLAUDE.md) | §5 ML pipeline — data layer + MANIFEST gate, QLoRA/DoRA training, quantization + ppl gate, the eval harness (benchmarks, 3C3H judges, fertility, efficiency), registry & release |
| [`apps/api/CLAUDE.md`](./apps/api/CLAUDE.md) | §7 FastAPI gateway — principles, v1 endpoint table, canonical patterns, testing bars |
| [`apps/web/CLAUDE.md`](./apps/web/CLAUDE.md) | §8 React 19 + R3F dashboard — design brief (ADR-0005), tokens, routes, 3D scenes, **bidi correctness**, quality bars |
| [`serving/CLAUDE.md`](./serving/CLAUDE.md) | §6 serving layer — vLLM (sovereign GPU), llama.cpp (CPU edge), the ModelRouter contract |
| [`infra/CLAUDE.md`](./infra/CLAUDE.md) | §9 IaC — OpenTofu modules, Helm charts, compose profiles, CI/CD workflows and the regression gate |

Two separate `uv` workspaces (`ml/` needs CUDA-heavy pins; `apps/api` stays slim) — **never merge
their dependency trees.**

---

## 3. Tech stack — pins and why

The lockfiles (`uv.lock`, `pnpm-lock.yaml`) are authoritative for versions, and each workspace's
manifest lists its own dependencies — read those rather than a table here. What is *not* derivable is
the ML stack's pin ceilings, because they interlock:

### 3.1 ML / training

| Area | Choice | Pin (floor) | Why (trend-aware) |
|---|---|---|---|
| Python | CPython | 3.12.x | Widest CUDA-wheel coverage; 3.13 wheels still lag for the training stack |
| Package mgr | **uv** (Astral) | ≥ 0.7 | The 2025–26 default; 10–100× faster than pip, lockfile-native, workspace support |
| Torch | torch + CUDA 12.x | ≥ 2.7 | SDPA/FlashAttention path; matches vLLM/Unsloth support matrix |
| Fine-tuning | **Unsloth** ≥ 2026.7 + TRL ≤ 0.24 + PEFT ≥ 0.18 | see `ml/pyproject.toml` | Unsloth = ~2× faster, 30–70% less VRAM on single GPU; PEFT gives `use_dora=True`. **TRL ≥ 1.0 is not available here** — Unsloth caps TRL at `<=0.24.0` in every release, and the former `trl>=1.0` floor silently resolved a year-old Unsloth that cannot import (ADR-0006). Unsloth's windows also cap transformers (`<=5.5`), datasets (`<4.4`) and torch (`<2.12`), which in turn caps `llmcompressor` at 0.10.x — raise any of these only together, and re-run `just preflight` |
| Quant (train) | bitsandbytes NF4 | ≥ 0.47 | QLoRA's training-safe 4-bit |
| Quant (GPU inference) | **llm-compressor** → AWQ W4A16 | ≥ 0.10, < 0.11 | AutoAWQ is archived; llm-compressor is the vLLM-official successor (produces `compressed-tensors` checkpoints vLLM loads natively). Ceiling is Unsloth's, not ours: 0.11 wants `datasets>=4.8.4` and 0.12 wants `transformers>=5.9`, both outside Unsloth's windows, and the two extras share one venv (ADR-0006) |
| Quant (edge) | llama.cpp GGUF **Q4_K_M + imatrix** | pinned commit | Q4_K_M = community sweet spot; importance-matrix quantization is the current quality trick — run imatrix on a **bilingual** calibration text |
| Experiment tracking | **MLflow** (self-hosted) | ≥ 2.20 | Sovereign-friendly (no SaaS); Trackio is an acceptable lighter alternative |
| Eval harness | **lm-evaluation-harness** | pinned commit ≥ 0.4.9 | Ships `arabicmmlu`, `arabic_leaderboard_*`; pin the exact rev in `run_lm_eval.sh` |
| Eval alt | LightEval | optional | OALL-v2/AraGen parity checks |
| Arabic NLP utils | CAMeL Tools, fasttext lid.176 | latest | Normalization for retrieval/dedup only — SFT keeps raw text |
| Dedup | text-dedup (MinHash) | latest | Standard near-dup removal before curation |

The choices elsewhere in the stack, with their sovereignty rationale: **vLLM** (V1 engine) for the
GPU server and **llama.cpp `llama-server`** at the edge, both speaking the OpenAI Chat Completions
dialect so ModelRouter only swaps base URLs · **FastAPI + Pydantic v2**, Postgres 17 + async
SQLAlchemy, Redis, **sse-starlette** for one-way token streams (SSE beats WebSockets with no CDN in
the path), structlog with a PII-scrub processor, self-hosted **Langfuse** optional · **React 19 +
Vite SPA** (no SSR server to harden in an air-gapped nginx deployment), R3F v9 + drei, Tailwind v4
CSS-first theming, **vendored** shadcn/ui primitives (copy-in = zero runtime CDN deps) · **OpenTofu**
HCL (open-source licensing), k3s + Helm, **Harbor + MinIO** self-hosted registries, **SOPS + age**
(no cloud KMS dependency), Trivy + Syft + cosign, **just** as the only command surface.

---

## 4. Environments, modes, and configuration

- One env var rules them all: `SANAD_MODE = dev | sovereign | edge`. Everything (pydantic-settings,
  compose profiles, Helm values, vite define) derives from it.
- **Offline enforcement (sovereign/edge):** export `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
  HF_DATASETS_OFFLINE=1 NO_PROXY=*`; web build must pass `just verify-no-cdn` (greps dist/ for
  `http(s)://` beyond same-origin + data: URIs); K8s `sovereign-guard` chart installs default-deny
  egress NetworkPolicies + the Prometheus egress alert.
- `.env` files are **never** committed; `infra/compose/.env.example` documents every variable.
  Real secrets live in `secrets/*.sops.yaml` (age recipients in `.sops.yaml`).
- The canonical settings shape is `apps/api/src/sanad_api/core/config.py` (pydantic-settings,
  `env_prefix="SANAD_"`). Two invariants it encodes: `allow_external_judges` is **forced False when
  `mode != "dev"`**, and `egress_allowed` is `mode == "dev"` — nothing else may decide egress.

---

## 5–9. Per-area specifications

Moved to the directory-scoped files in [§2](#2-where-the-rest-of-this-spec-lives). Section numbering
is preserved inside them, so cross-references like "§5.3's accuracy clause" or "§8.4a" still resolve.

---

## 10. Security & sovereignty checklist (audited per release)

Run `just sovereign-audit` — it executes every item below that does not need a live cluster and
**names the three that do** rather than counting them as green. It gates CI (`sovereignty` job).
`ops/verify-artifacts.sh` is the cosign verify path: signing without verification proves nothing to
whoever pulls the artifact.

- [ ] `SANAD_MODE=sovereign` sets all offline env vars; boot fails loudly if a model dir is missing (no silent hub fetch)
- [ ] `sovereign-guard` NetworkPolicies applied; egress-zero alert green for 24 h before demo
- [ ] All images: Trivy high/critical = 0 (or documented waiver), SBOM attached, cosign-signed; Harbor policy blocks unsigned
- [ ] Model artifacts sha256-verified on every sync (edge `mc mirror` + initContainer)
- [ ] License matrix in `MANIFEST.yaml` + model `manifest.json` consistent with prime directive 2
- [ ] No third-party CDN/fonts/analytics in `web/dist` (`just verify-no-cdn`)
- [ ] Secrets only via SOPS+age; `git secrets`-style pre-commit hook active
- [ ] Logs PII-scrubbed (structlog processor: mask emails/IBAN/EID patterns — AR + EN regexes); chat content not persisted by default
- [ ] Judges in sovereign mode are local-only; API-judge scores flagged `sovereign=false` and excluded from headline metrics

---

## 11. Quality gates (CI-enforced)

| Layer | Tool | Gate |
|---|---|---|
| ml/ | ruff + mypy + pytest | schema validators + manifest gen covered; `data-gate` license check |
| Training | MLflow + budget log | peak VRAM < 16 GB; cost logged, $0 target (free-tier compute, ADR-0003) |
| Quantization | `ppl_gate.py` | ΔPPL ≤ 3% (AWQ) / 5% (GGUF); ArabicMMLU drop ≤ 1.0 pt |
| Eval | eval.yml regression gate | domain ≥ base +5 pts; ArabicMMLU ≥ base −1 pt; judge claims require human-κ present |
| api | pytest cov ≥ 80% + schemathesis | OpenAPI fuzz clean; SSE proxy chunk-integrity test |
| web | biome + tsc + vitest + Playwright | RTL+LTR snapshots; logical-properties grep; Lighthouse ≥ 90 / ≥ 75 (hero) |
| Images | Trivy + Syft + cosign | 0 high/critical; signed |
| Infra | tofu validate + tflint + `helm lint` | plan reviewed on PR |

## 12. Command surface (`justfile` — keep this the only entry point)

`just --list` is the current, authoritative surface — read it rather than a copy. The justfile is the
only entry point: setup, data pipeline + gate, preflight, train/merge, quantize + ppl gate, eval,
judge, fertility, registry push, the dev/gpu/edge compose stacks, `check`, verify-no-cdn, the tofu
and helm wrappers, and `bench-edge`. Add commands there rather than documenting ad-hoc invocations.

### 12.1 Inner-loop shortcuts (`just check` runs everything; these run one thing)

`just check` is the full PR gate. While iterating, run a single workspace/test directly — the two
`uv` workspaces are independent, so `cd` into the one you're touching. Tool config lives in each
workspace's `pyproject.toml` (web: `biome.json`): both Python stacks = ruff (line 100; RUF001–003
ignored — Arabic text is deliberate) + mypy `strict = true`; `apps/api` adds `pydantic.mypy`,
`asyncio_mode = "auto"`, respx-mocked upstreams and an in-memory aiosqlite test DB, and its pytest
gate (CI **and** `just check`) enforces `--cov-fail-under=80` on `services/` + `routers/`.

```bash
# ml/ — training/quant/eval workspace (no GPU extras needed for lint/test)
cd ml && uv run pytest tests/test_gates.py::test_gate_blocks_planted_noncommercial_record -q
cd ml && uv run ruff check . && uv run mypy .

# apps/api — FastAPI gateway (async tests, respx-mocked upstreams)
cd apps/api && uv run pytest tests/test_chat_sse.py -k name -q   # one file / keyword
cd apps/api && uv run pytest -q --cov=src/sanad_api/services --cov=src/sanad_api/routers --cov-fail-under=80

# apps/web — React/R3F dashboard
cd apps/web && pnpm exec vitest --run tests/bidi.test.ts         # one vitest file (`pnpm test` = watch mode)
cd apps/web && pnpm exec biome check . && pnpm exec tsc --noEmit
cd apps/web && pnpm exec playwright test e2e/rtl-ltr.spec.ts     # e2e — builds + serves preview itself
                                                                 # (`pnpm exec playwright install chromium` once, online)
```

GPU-heavy ML deps are optional extras — `uv sync` alone (via `just setup`) installs only the slim
lint/test set; add `--extra train` / `--extra quant` / `--extra arabic` on a train box. Regenerate
the web API client after any endpoint change: `just api-types` (output in `apps/web/src/lib/api/`
is generated — never hand-edit).

## 13. Implementation roadmap (phases = PR milestones; each has acceptance criteria)

**P0 · Skeleton (wk 1).** Monorepo tree, justfile, CI (lint/type/test green on hello-world),
compose dev stack up, tokens.css + app shell with EN/AR toggle + RTL flip. ✓ = `just check`
green; RTL snapshot passes.

**P1 · Data (wk 2–3).** Ingest CIDAR, curation template + first 300 own banking pairs,
dedup/langid, MANIFEST + data-gate. ✓ = manifest shows provenance split; gate blocks a planted
non-commercial record.

**P2 · Train + merge (wk 3–4).** sft.py on the local RTX 4090 (ADR-0004; bf16, canonical
config unchanged; Kaggle/Colab = fallback only), MLflow run, merged-bf16 + manifest.
✓ = VRAM < 16 GB; cost logged = $0; val loss curve archived.

**P3 · Quantize + serve (wk 4–5).** AWQ + GGUF (+imatrix), ppl-gate, vLLM chart on k3s/k3d (or
compose gpu), CPU edge via compose `edge` profile, `bench-edge` numbers recorded. ✓ = both
gates pass; edge tok/s (+ watts where RAPL readable) in a report labeled `x86-local`.

**P4 · Eval harness (wk 5–6).** lm-eval across model matrix, domain eval v1 (300 items frozen),
3C3H judges + agreement + 50-item human validation. ✓ = regression gate wired; human-κ reported;
headline table generated.

**P5 · Full app (wk 6–7).** Chat SSE end-to-end (bidi-safe streaming), FertilityField hero with
live `/v1/tokenize/fertility`, Evals + Edge + Registry pages, PipelineOrbit + EdgeBoard scenes,
telemetry SSE. ✓ = Lighthouse bars met; sovereign compose demo runs with Wi-Fi off.

**P6 · Sovereign hardening (wk 7).** sovereign-guard chart, egress alert, cosign verify path,
SBOMs, PII scrubbing tests, checklist §10 fully green. ✓ = 24 h egress-zero on demo cluster.

**P7 · Position + publish (wk 8).** README with headline results + architecture GIF, model card,
blog/LinkedIn post, paper draft (`docs/paper/`, scope: reproducible recipe + eval harness +
fertility/edge measurements — **no frontier-beating claims**), CV bullets with real numbers.

**Decision thresholds (from the research blueprint — honor them):** SLM fails to match the large
model in-domain → narrow the domain or add curated data before touching model size · CPU-edge
latency unacceptable → smaller quant (Q4_K_S/IQ4_XS) or shorter context; keep vLLM+AWQ as the
server story · commercial licensing hard-requirement → Apache-2.0 matrix only (already default).

## 14. Working agreements for Claude Code

1. Read §0 directives before any task; when a request conflicts with them, say so and propose a
   compliant alternative.
2. Touch one phase per PR; conventional commits (`feat(api): …`); update this file + an ADR for
   any architectural change.
3. Never add a dependency without a one-line justification in the PR body; never bypass lockfiles.
4. Bilingual strings: adding an `en/*.json` key without its `ar/*.json` sibling fails CI — write
   real Arabic (MSA), mark machine-drafted strings with `"_review": "pending-native"` until
   reviewed.
5. Generated things (API client, fertility.json, reports) are never hand-edited.
6. All numbers quoted in README/paper must trace to a report file in `ml/evals/reports/` by hash.
7. Before declaring any task done: `just check`, and for UI work attach LTR+RTL screenshots.

## 15. Pinned reference matrix

| Asset | ID | License | Role |
|---|---|---|---|
| Qwen3-4B-Instruct | `Qwen/Qwen3-4B-Instruct-2507` (pin rev) | Apache-2.0 | primary base |
| ALLaM-7B | `humain-ai/ALLaM-7B-Instruct-preview` | Apache-2.0 | Arabic-native comparator + judge |
| jais-family-6.7b | `inceptionai/jais-family-6p7b-chat` | Apache-2.0 | Arabic-native comparator |
| Falcon-H1-Arabic 3B/7B | TII HF org (pin) | Falcon-LLM License | SOTA comparator + judge (7B) |
| CIDAR | `arbml/CIDAR` | Apache-2.0 | native instruction core |
| ArabicMMLU / AraTrust / MadinahQA / ALRAGE | via lm-eval tasks | per-set | benchmarks |
| AraFinNews | (quarantine) | **non-commercial** | research-only experiments |
| lm-evaluation-harness | EleutherAI @ pinned commit | MIT | harness |

**Verified on Hugging Face 2026-07-25.** The three resolved pins (Qwen3-4B revision, llama.cpp
commit, lm-eval commit) live in the configs that consume them —
`configs/train/qwen3-4b-qlora-dora.yaml`, `configs/quant/gguf-q4km.yaml`,
`evals/harness/run_lm_eval.sh` — read them there so a quoted sha cannot drift from the one in use.

`sft.py` enforces that `revision` is a 40-char lowercase commit sha — a branch or tag would let a
rerun train against different weights, so neither passes the gate.

**Two access prerequisites, both discovered at verification and neither automatable:**

- `meta-llama/Llama-3.2-3B-Instruct` is **`gated: manual`** — Meta approves each request by hand.
  Its tokenizer is one of the five in the fertility comparison (§5.4d), so `just fertility` cannot
  produce a complete table until that approval lands. Request it early; it is the long-lead item.
- `inceptionai/jais-family-6p7b-chat` is **`gated: auto`** — accept the terms once while online and
  the download proceeds; the sync needs an `HF_TOKEN` present.

**ALLaM ships no `tokenizer.json`** — sentencepiece-only layout. Both fertility consumers read
`tokenizer.json` and nothing else (the API's loader has no sentencepiece path at all), so ALLaM is
simply absent from the fertility table unless converted. `sync_tokenizers.py` converts it via
`transformers` (`train` extra); without that extra it reports the requirement instead of failing.

**ALLaM moved orgs**: `ALLaM-AI/` → `humain-ai/`. Hugging Face serves a 307 for the old path, so a
browser follows it silently, but an offline mirror pass resolves ids literally and would fail. The
table and all four code references were corrected; treat this as the standing reason to re-verify
ids rather than trust them.

*Everything else above was current as of early 2026 — re-verify on Hugging Face at bootstrap time,
since newer checkpoints may exist.*

---
*End of CLAUDE.md — if you're Claude Code and you read this far: run `just --list`, pick the
current phase from §13, and open a small PR.*
