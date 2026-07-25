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

> **⚠️ Current repository state (as of 2026-07-15): P0 COMPLETE — `just check` GREEN, RTL/LTR
> snapshots GREEN.** The full §2 tree exists (see ADR-0002 for in-spec implementation choices, ADR-0005 for the §8 design direction),
> lockfiles are generated, `just check` passes end-to-end (ruff+mypy+pytest both Python
> workspaces, biome+tsc+vitest+i18n-sync web, data-gate, verify-no-cdn), and Playwright RTL+LTR
> snapshots pass for all 6 routes (baselines in `apps/web/e2e/rtl-ltr.spec.ts-snapshots/`).
> The P1–P5 *source* is written but the pipeline has never been executed: no data ingested
> (MANIFEST zeroed), domain eval holds 12/300 items, no reports, no model artifacts.
> **Next: P1 (data).** The Qwen3 revision, llama.cpp commit and `LM_EVAL_REV` pins are filled and
> verified (§15). Two prerequisites remain and neither is automatable: the **age recipient in
> `.sops.yaml`** needs the owner's own key (`age-keygen`), and **`meta-llama/Llama-3.2-3B-Instruct`
> is manually gated** — request access early, since its tokenizer is one of the five in the
> fertility table. Remove this notice when P1 lands.

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

## 2. Monorepo layout

```
sanad/
├── CLAUDE.md                     # this file — read first
├── justfile                      # all commands (just = task runner; `just --list`)
├── .github/workflows/            # ci.yml · eval.yml · release.yml
├── .pre-commit-config.yaml
├── ml/                           # Python workspace #1 (uv) — training/quant/eval
│   ├── pyproject.toml
│   ├── configs/
│   │   ├── train/qwen3-4b-qlora-dora.yaml
│   │   ├── quant/awq-w4a16.yaml · quant/gguf-q4km.yaml
│   │   └── eval/{oall_native.yaml, domain_bank.yaml, judge_3c3h.yaml}
│   ├── data/
│   │   ├── MANIFEST.yaml         # counts, licenses, provenance split, sha256 — CI license gate
│   │   ├── schemas/record.schema.json
│   │   ├── scripts/{ingest_cidar.py, curate_bank.py, dedup.py, langid.py, normalize.py}
│   │   ├── raw/ processed/       # gitignored; DVC-style pointers optional
│   │   └── quarantine/           # research-only sets (AraFinNews, …) — never in commercial manifest
│   ├── train/{sft.py, merge.py, chat_template.py}
│   ├── quantize/{awq.py, gguf.sh, ppl_gate.py}
│   ├── evals/
│   │   ├── harness/run_lm_eval.sh          # pinned rev + task configs
│   │   ├── domain/sanad_bank_eval_v1.jsonl # 300 held-out items (own-authored, CC-BY-4.0)
│   │   ├── judge/{run_judges.py, rubric_ar.md, rubric_en.md, agreement.py, human_validation.md}
│   │   ├── fertility/measure.py            # tokens/word across tokenizers → JSON for web hero
│   │   └── reports/                        # generated md+json → ingested by API
│   └── registry/{push.py, manifest.py}     # MinIO artifact push + manifest.json
├── apps/
│   ├── api/                      # Python workspace #2 (uv) — FastAPI gateway
│   │   ├── pyproject.toml
│   │   ├── src/sanad_api/
│   │   │   ├── main.py
│   │   │   ├── core/{config.py, logging.py, security.py, metrics.py}
│   │   │   ├── routers/{chat.py, models.py, evals.py, telemetry.py, tokenize.py, registry.py, health.py}
│   │   │   ├── services/{inference_router.py, fertility.py, registry.py, judge_ingest.py}
│   │   │   ├── db/{models.py, session.py}
│   │   │   └── schemas/{chat.py, evals.py, telemetry.py, common.py}
│   │   ├── migrations/           # alembic
│   │   └── tests/                # pytest-asyncio + respx + schemathesis
│   └── web/                      # pnpm — React 19 + Vite + R3F 3D dashboard
│       ├── package.json · vite.config.ts · biome.json · index.html
│       ├── src/
│       │   ├── app/{routes.tsx, providers.tsx}
│       │   ├── pages/{Home.tsx, Chat.tsx, Evals.tsx, TokenizerLab.tsx, Edge.tsx, Registry.tsx}
│       │   ├── three/            # 3D scenes (see §8.4)
│       │   │   ├── FertilityField/ · PipelineOrbit/ · EdgeBoard/
│       │   │   └── lib/{useTokenClusters.ts, glyphAtlas.ts, perf.ts}
│       │   ├── components/{chat/, evals/, ui/}   # shadcn/ui-derived primitives
│       │   ├── i18n/{index.ts, ar/*.json, en/*.json}
│       │   ├── lib/{api/ (generated), sse.ts, bidi.ts, format.ts}
│       │   ├── styles/{tokens.css, global.css}   # Tailwind v4 @theme
│       │   └── store/{ui.ts, tokenizer.ts}       # zustand
│       └── tests/ (vitest) · e2e/ (playwright)
├── serving/
│   ├── vllm/{Dockerfile, entrypoint.sh}
│   └── llamacpp/run.sh            # CPU edge launcher (image: ghcr llama.cpp, compose `edge` profile)
├── infra/
│   ├── terraform/                # OpenTofu-compatible HCL
│   │   ├── envs/{dev, prod}/main.tf
│   │   └── modules/{gpu_train, k3s_cluster, registry_minio_harbor, observability, network}
│   ├── helm/charts/{sanad-api, sanad-web, vllm, eval-job, sovereign-guard}
│   └── compose/{docker-compose.yml, compose.sovereign.yml, compose.edge.yml}
├── ops/{dashboards/, alerts/, runbooks/}
└── docs/{adr/, paper/, model-cards/, screenshots/}
```

Two separate `uv` workspaces (`ml/` needs CUDA-heavy pins; `apps/api` stays slim) — never merge
their dependency trees.

---

## 3. Tech stack — choices, pins, and why (state of the art as of mid-2026)

Version numbers below are **known-good floors**; the lockfiles are authoritative. When
bootstrapping, run `uv lock` / `pnpm install` and trust resolution; do not hand-edit locks.

### 3.1 ML / training

| Area | Choice | Pin (floor) | Why (trend-aware) |
|---|---|---|---|
| Python | CPython | 3.12.x | Widest CUDA-wheel coverage; 3.13 wheels still lag for the training stack |
| Package mgr | **uv** (Astral) | ≥ 0.7 | The 2025–26 default; 10–100× faster than pip, lockfile-native, workspace support |
| Torch | torch + CUDA 12.x | ≥ 2.7 | SDPA/FlashAttention path; matches vLLM/Unsloth support matrix |
| Fine-tuning | **Unsloth** + TRL ≥ 1.0 + PEFT ≥ 0.17 | latest | Unsloth = ~2× faster, 30–70% less VRAM on single GPU; TRL v1 unified `SFTTrainer`; PEFT gives `use_dora=True` |
| Quant (train) | bitsandbytes NF4 | ≥ 0.47 | QLoRA's training-safe 4-bit |
| Quant (GPU inference) | **llm-compressor** → AWQ W4A16 | ≥ 0.6 | AutoAWQ is archived; llm-compressor is the vLLM-official successor (produces `compressed-tensors` checkpoints vLLM loads natively) |
| Quant (edge) | llama.cpp GGUF **Q4_K_M + imatrix** | pinned commit | Q4_K_M = community sweet spot; importance-matrix quantization is the current quality trick — run imatrix on a **bilingual** calibration text |
| Experiment tracking | **MLflow** (self-hosted) | ≥ 2.20 | Sovereign-friendly (no SaaS); Trackio is an acceptable lighter alternative |
| Eval harness | **lm-evaluation-harness** | pinned commit ≥ 0.4.9 | Ships `arabicmmlu`, `arabic_leaderboard_*`; pin the exact rev in `run_lm_eval.sh` |
| Eval alt | LightEval | optional | OALL-v2/AraGen parity checks |
| Arabic NLP utils | CAMeL Tools, fasttext lid.176 | latest | Normalization for retrieval/dedup only — SFT keeps raw text |
| Dedup | text-dedup (MinHash) | latest | Standard near-dup removal before curation |

### 3.2 Serving

| Area | Choice | Pin | Why |
|---|---|---|---|
| GPU server | **vLLM** (V1 engine) | ≥ 0.9 | Highest-throughput OSS server; native AWQ/compressed-tensors, prefix caching, OpenAI-compatible |
| Edge | **llama.cpp `llama-server`** | pinned image digest | CPU-only x86 serving of the GGUF artifact; OpenAI-compatible; measured via `just bench-edge` |
| Contract | OpenAI Chat Completions API | — | Everything upstream of the gateway speaks one dialect; ModelRouter just swaps base URLs |

### 3.3 Backend (apps/api)

| Area | Choice | Pin | Why |
|---|---|---|---|
| Framework | **FastAPI** + Pydantic v2 | ≥ 0.116 / ≥ 2.11 | Still the Python API standard; Pydantic v2 core is Rust-fast |
| Server | uvicorn (granian optional) | ≥ 0.35 | Granian (Rust ASGI) is the trending alternative; keep uvicorn default for ecosystem safety |
| DB | PostgreSQL 17 + SQLAlchemy 2.0 async + asyncpg + Alembic | ≥ 2.0.41 | Boring, correct; stores runs/metrics/judge scores/telemetry |
| Cache/queues | Redis 7 | redis-py ≥ 6 | Token-bucket rate limit + pub/sub fan-out for telemetry SSE |
| Streaming | **sse-starlette** | ≥ 2.3 | SSE > WebSockets for one-way token streams (proxies/CDN-free, auto-reconnect) |
| HTTP client | httpx (async, pooled) | ≥ 0.28 | Upstream calls to vLLM/llama.cpp |
| Logging | structlog (JSON) + PII-scrub processor | ≥ 25 | Sovereign logs must never leak prompts with PII |
| Metrics/traces | prometheus-client + OpenTelemetry SDK | latest | Grafana dashboards in `ops/dashboards` |
| LLM traces | **Langfuse (self-hosted)** — optional | v3 | The sovereign-deployable LLM observability pick |
| Lint/type | **ruff** (lint+fmt) + mypy --strict | ≥ 0.11 / ≥ 1.15 | Ruff replaced black+isort+flake8 everywhere |
| Tests | pytest + pytest-asyncio + respx + **schemathesis** | latest | Schemathesis fuzzes the OpenAPI contract — a strong production signal |

### 3.4 Frontend (apps/web)

| Area | Choice | Pin | Why |
|---|---|---|---|
| Runtime | Node 22 LTS + **pnpm** | pnpm ≥ 10 | Workspace-fast, content-addressed store |
| Build | **Vite** | ≥ 6 | SPA is the right shape for an air-gapped nginx-served dashboard (no SSR server to harden) |
| UI | **React 19** + TypeScript | ≥ 19.1 / TS ≥ 5.8 | R3F v9 requires React 19 |
| 3D | **@react-three/fiber v9 + drei v10 + three (r17x) + @react-three/postprocessing** | ^9 / ^10 | The de-facto 2026 React 3D stack; declarative scenes, instancing, ScrollControls |
| Styling | **Tailwind CSS v4** (CSS-first `@theme`) | ≥ 4.1 | v4's CSS-variable-native theming maps 1:1 to our token file; logical properties for RTL |
| Components | shadcn/ui primitives (Radix + CVA), vendored | — | Copy-in components = zero runtime CDN deps (sovereign) |
| Motion | **motion** (framer-motion v12 rebrand) | ^12 | Page/element transitions outside the Canvas |
| State | zustand v5 (UI/3D shared) + **TanStack Query v5** (server) | ^5 | Query owns caching/retries; zustand bridges DOM ⇄ Canvas |
| i18n / RTL | react-i18next + `dir` switching + `Intl.Segmenter` | i18next ≥ 24 | Grapheme-safe Arabic streaming (see §8.6) |
| API types | **@hey-api/openapi-ts** generated client | latest | Types generated from FastAPI's OpenAPI — zero drift |
| Fonts (self-hosted) | @fontsource: Fraunces var (Latin display), Aref Ruqaa (AR display), IBM Plex Sans + Plex Sans Arabic (body/UI, one superfamily), Plex Mono (data/labels) | latest | No Google Fonts CDN in sovereign mode — ever; script-subsetted (ADR-0005) |
| Lint/format | **Biome** | ≥ 1.9 | Single fast tool replacing eslint+prettier; keep a11y rules on |
| Tests | Vitest + Testing Library + Playwright (RTL+LTR snapshots) | latest | Bidi regressions are the #1 bug class here |

### 3.5 Infra / IaC / DevOps

| Area | Choice | Pin | Why |
|---|---|---|---|
| IaC | **OpenTofu-compatible HCL** (works on Terraform ≥ 1.10 too) | tofu ≥ 1.8 | OpenTofu = open-source, sovereign-friendly licensing; S3-native state locking (no DynamoDB) |
| Cloud burst | `gpu_train` module (AWS me-central-1) — **plan-only artifact, never applied** | — | Training runs on the local RTX 4090 (ADR-0004); module kept as reviewable IaC |
| On-prem K8s | **k3s** v1.32 + Helm ≥ 3.17 | — | The 2026 default for edge/on-prem lightweight clusters |
| Registry | **Harbor** (images) + **MinIO** (models/artifacts) | ≥ 2.12 / latest | Self-hosted, air-gap replicable; Harbor scans + signs |
| Secrets | **SOPS + age** | ≥ 3.10 | Git-native encrypted secrets, no cloud KMS dependency |
| Supply chain | Trivy (scan) + **Syft SBOM** + **cosign** sign/verify | latest | 2026 table stakes; sovereign admission verifies signatures |
| Observability | kube-prometheus-stack + **dcgm-exporter** (GPU) + Loki + llama-server `/metrics` (edge) | latest | Includes the signature **egress-zero alert** for sovereign namespaces |
| CI/CD | GitHub Actions (free tier, public repo) | — | eval.yml = `workflow_dispatch` ingesting locally produced eval reports (ADR-0003/0004; no self-hosted GPU runner) |
| Task runner | **just** | ≥ 1.36 | Readable, cross-platform command surface (`just --list`) |

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

```python
# apps/api/src/sanad_api/core/config.py — canonical settings shape
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SANAD_", env_file=".env")
    mode: Literal["dev", "sovereign", "edge"] = "dev"
    vllm_base_url: str = "http://vllm:8000/v1"
    llamacpp_base_url: str = "http://llamacpp:8080/v1"
    database_url: str = "postgresql+asyncpg://sanad:sanad@postgres:5432/sanad"
    redis_url: str = "redis://redis:6379/0"
    registry_s3_endpoint: str = "http://minio:9000"
    allow_external_judges: bool = False          # forced False when mode != "dev"
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def egress_allowed(self) -> bool:
        return self.mode == "dev"
```

---

## 5. ML pipeline specification

### 5.1 Data layer

**Record schema** (`ml/data/schemas/record.schema.json`) — every SFT/eval record validates against:

```json
{
  "id": "bank-ar-000142",
  "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "lang": "ar | en | mixed",
  "domain": ["banking.compliance", "banking.retail", "general"],
  "provenance": "native | translated | synthetic",
  "source": {"name": "CIDAR", "url": "hf:arbml/CIDAR", "license": "Apache-2.0"},
  "pii_checked": true,
  "split": "train | val | test"
}
```

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
Jaccard ≥ 0.85 drop) → schema validation → `MANIFEST.yaml` regeneration.

**`MANIFEST.yaml` is a CI gate:** aggregates per-source counts, license, provenance split
(native/translated/synthetic %), sha256 of the processed shards, and a `profile:` field.
`just data-gate` fails if any record's license ∉ {Apache-2.0, CC-BY-4.0, MIT} while
`profile: commercial`. The native-vs-translated split is printed into every eval report (rigor
signal — see research doc §2).

### 5.2 Fine-tuning (Unsloth QLoRA + DoRA)

Canonical config — `ml/configs/train/qwen3-4b-qlora-dora.yaml` (train/sft.py consumes this; any
hyperparameter change = new file, never mutate):

```yaml
base_model: Qwen/Qwen3-4B-Instruct-2507      # Apache-2.0; pin exact revision sha in lockfile below
revision: "<pin-hf-commit-sha>"
seed: 3407
max_seq_len: 4096
load_in_4bit: true                            # NF4 (bitsandbytes)
lora: {r: 16, alpha: 16, dropout: 0.0, use_dora: true, target_modules: all-linear}
train:
  epochs: 3
  lr: 2.0e-4
  scheduler: cosine
  warmup_ratio: 0.03
  per_device_batch: 4
  grad_accum: 4                               # effective 16
  packing: true
  bf16: true
  optim: adamw_8bit
  neftune_noise_alpha: 5                      # cheap robustness bump; ablate once
chat_template: qwen3                          # train non-thinking mode: enable_thinking=false
eval_holdout: data/processed/val.jsonl
logging: {mlflow_experiment: sanad-sft, log_steps: 10}
outputs: {adapter_dir: out/adapter, merged_dir: out/merged-bf16}
```

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

### 5.3 Quantization

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

### 5.4 Evaluation harness (the credibility core)

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

**(d) Tokenizer fertility (`fertility/measure.py`):** tokens/word for {Qwen3, jais-family, ALLaM,
Falcon-H1, Llama-3.2} tokenizers over three fixed corpora (MSA news 10k words, banking-domain 5k,
English 10k). Outputs `fertility.json` → consumed by the API and the 3D hero. This is the
project's signature insight: fertility ≈ latency ≈ cost ≈ effective context for Arabic.

**(e) Efficiency panel:** TTFT, tok/s (prompt+gen), peak VRAM/RSS, watts (CPU edge via RAPL;
GPU via DCGM), $/1M output tokens (electricity+amortization model in `evals/reports/cost_model.md`).

### 5.5 Model registry & release

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

---

## 6. Serving layer

### 6.1 vLLM (sovereign GPU server)

`serving/vllm/entrypoint.sh` (values templated by Helm/compose):

```bash
exec vllm serve /models/sanad-qwen3-4b-bank/awq-w4a16 \
  --served-model-name sanad-bank-awq \
  --max-model-len 8192 --gpu-memory-utilization 0.90 \
  --enable-prefix-caching --disable-log-requests \
  --host 0.0.0.0 --port 8000
```

Notes: model dir is a read-only PVC synced from MinIO by an initContainer (`mc mirror`);
quantization is auto-detected from the compressed-tensors checkpoint — don't pass legacy
`--quantization awq` flags unless vLLM asks; probe `/health`; one model per pod (HPA on
`num_requests_waiting`).

### 6.2 llama.cpp (CPU edge — ADR-0004)

- Image: `ghcr.io/ggml-org/llama.cpp:server` (pin a digest before P3), CPU-only x86; launched
  by the compose `edge` profile or `serving/llamacpp/run.sh`.
- Run: `llama-server -m /models/sanad-Q4_K_M.gguf -c 4096 --host 0.0.0.0 --port 8080
  --parallel 2 --metrics` (no `-ngl` — the edge demo is deliberately GPU-free to prove the
  CPU-only deployment shape).
- Envelope for a 4B Q4_K_M: ~2.5–3 GB weights + ~0.5–1.5 GB KV in RAM. **Benchmark on the
  actual host/llama.cpp pair and record it** — `just bench-edge`
  (`ops/runbooks/edge-bench.md`), which also samples package watts via Intel RAPL when
  readable; results labeled `platform: x86-local`.
- Telemetry: llama-server `/metrics` + the dev-mode demo publisher feed
  `sanad_edge_watts`, `sanad_edge_gpu_util`, `sanad_edge_temp_c` via the API SSE bridge.

### 6.3 ModelRouter contract

The API never hardcodes upstreams. `services/inference_router.py` maps
`model_alias → {upstream_kind: vllm|llamacpp, base_url, served_name}` from the registry table;
health-checks upstreams every 15 s; exposes availability in `/v1/models`.

---

## 7. Backend — apps/api (FastAPI)

### 7.1 Principles

Async end-to-end; OpenAI-compatible passthrough for chat (so any OSS client works) **augmented**
with Sanad metadata (latency, token usage, detected lang, sovereign flag); strict CORS from
settings; security headers middleware (CSP self-only, X-Content-Type-Options, HSTS in prod);
problem+json error shape; Redis token-bucket rate limit (per-IP dev, per-key prod); every route
carries Prometheus histograms (`sanad_api_request_seconds{route,method,status}`).

### 7.2 Endpoints (v1)

| Method & path | Purpose |
|---|---|
| `POST /v1/chat/completions` | OpenAI-compatible; streams SSE when `stream=true`; routes by `model` alias; appends `x_sanad` usage block on final chunk |
| `GET /v1/models` | Aliases + upstream health + quant format + license from manifests |
| `GET /v1/eval/runs` · `GET /v1/eval/runs/{id}` | Benchmark scores, 3C3H per-dim, agreement stats (α, κ, heatmap), efficiency panel |
| `POST /v1/eval/runs/{id}/ingest` | CLI/K8s eval-job posts `reports/*.json` here (bearer service token) |
| `GET /v1/telemetry/stream` | SSE fan-out of edge/GPU metrics (Redis pub/sub bridge) |
| `POST /v1/tokenize/fertility` | `{text}` → per-tokenizer token counts/segments (powers the 3D hero) |
| `GET /v1/registry/artifacts` | Model versions, sha256, cosign status, lineage graph |
| `GET /healthz` · `GET /readyz` | Liveness (process) / readiness (DB+Redis+≥1 upstream) |

### 7.3 Canonical patterns (copy these shapes)

```python
# main.py — lifespan wiring
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from sanad_api.core.config import Settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    s = Settings()
    app.state.settings = s
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5))
    # init: async engine, redis pool, model router refresh task
    yield
    await app.state.http.aclose()

app = FastAPI(title="sanad-api", version="1.0.0", lifespan=lifespan)
# include_router(chat, models, evals, telemetry, tokenize, registry, health)
```

```python
# routers/chat.py — SSE proxy core (trimmed to the essential shape)
from sse_starlette.sse import EventSourceResponse

@router.post("/v1/chat/completions")
async def chat(req: ChatRequest, request: Request):
    upstream = request.app.state.router.resolve(req.model)      # vllm | llamacpp
    payload = req.model_dump(exclude_none=True)
    if not req.stream:
        r = await request.app.state.http.post(f"{upstream.base_url}/chat/completions", json=payload)
        return augment_usage(r.json(), upstream)                # adds x_sanad block

    async def gen():
        async with request.app.state.http.stream(
            "POST", f"{upstream.base_url}/chat/completions", json=payload
        ) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    yield {"data": line[6:]}                    # passthrough OpenAI chunks
        yield {"data": final_stats_chunk(upstream)}             # x_sanad: ttft, tok/s, lang
    return EventSourceResponse(gen(), ping=15000)
```

DB tables (SQLAlchemy 2.0, Alembic-managed): `eval_runs`, `benchmark_scores`, `judge_scores`
(judge, dim, score, item_id), `agreement_stats`, `artifacts`, `telemetry_snapshots`,
`chat_usage`. Chat **content is not persisted** by default (sovereign posture) — only usage
metadata; a `SANAD_PERSIST_CHATS=true` dev flag exists for debugging.

### 7.4 Backend testing

pytest-asyncio unit tests for services; respx-mocked upstream tests for the SSE proxy (assert
chunk passthrough + final x_sanad frame); schemathesis run against the live OpenAPI in CI;
Alembic migration up/down smoke; coverage gate ≥ 80% on `services/` + `routers/`.

---

## 8. Frontend — apps/web (React 19 + R3F 3D dashboard)

### 8.1 Design brief (deliberate, not default) — see ADR-0005

Subject: a sovereign bilingual model platform for Gulf banking. Audience: UAE ML hiring managers
and researchers who will judge craft in 90 seconds. The page's job: prove Arabic-first
engineering depth instantly. **The signature element is the Specimen (§8.4a):** the bilingual
sentence set intact at display size, with a measured rule beneath it broken into one dash per
token, re-cutting live as you switch tokenizer — the project's core insight as evidence you can
read, not an effect you watch. Everything else stays quiet and disciplined so that one moment
carries the identity. Explicitly avoid the stock AI looks (cream+serif+terracotta;
near-black+acid-green; broadsheet hairlines) — this design's identity comes from **dual-script
typography treated as material** and a **lamplit-manuscript ground with rubricator's pigments
as instrumentation**.

### 8.2 Design tokens (`src/styles/tokens.css`, Tailwind v4 `@theme`)

```css
@import "tailwindcss";
@theme {
  /* Palette — "Rubrication": warm ink canvas, rag-paper text, copper-green + red-lead instruments */
  --color-ink-950: #171310;       /* app canvas — warm ink black */
  --color-ink-900: #1F1A15;       /* raised surfaces */
  --color-ink-850: #262019;       /* wells, inset fields */
  --color-ink-700: #3A3229;       /* hairline rules, grid */
  --color-ink-600: #4E4437;       /* stronger rule, hover border */
  --color-sand-100: #F4ECDD;      /* primary text — and the Arabic script's colour */
  --color-sand-300: #C9BCA5;      /* mid text */
  --color-sand-400: #A2947E;      /* secondary text, labels */
  --color-pewter-400: #8FA7BD;    /* Latin script marker (fertility visuals only) */
  --color-verdigris-400: #3FBFA4; /* the one instrument accent: live numbers, active, pass */
  --color-cinnabar-400: #E4603F;  /* alarms only: failed gates, stream errors */
  /* Type — two calligraphic display faces from unrelated traditions, one neutral superfamily under */
  --font-display: "Fraunces Variable", Georgia, serif; /* Latin display (WONK 1, SOFT 0) */
  --font-ar-display: "Aref Ruqaa", serif;             /* Arabic display — Ruqaa calligraphy, 700 */
  --font-body: "IBM Plex Sans", sans-serif;           /* Latin body/UI */
  --font-ar: "IBM Plex Sans Arabic", sans-serif;      /* Arabic body/UI — same superfamily */
  --font-mono: "IBM Plex Mono", ui-monospace, monospace; /* data, tokens, hashes, eyebrow labels */
  --radius-panel: 0.25rem;        /* ruled document, not a card deck */
  --shadow-panel: 0 1px 0 0 var(--color-ink-700);
}
```

Rules: fluid type via `clamp()` (Latin display 2.1–4.25rem, Arabic 1.9–3.6rem — Ruqaa needs more
leading and no negative tracking); `:lang(ar)` swaps to `--font-ar` and bumps line-height to 1.8;
**`font-size-adjust: 0.5` on the Arabic display face** — Ruqaa draws small for its em, and matching
x-heights rather than font-sizes is what makes the two scripts land as equals (prime directive 3);
`opsz` is left unset on Fraunces so `font-optical-sizing: auto` tracks it to the rendered size;
verdigris appears only on live numbers, active nav and the cheapest row — never as large fills;
sections are separated by hairline `.rule-top` bands rather than bordered cards; `.eyebrow` is the
one repeated label form (spaced mono small caps in Latin, weight-differentiated in Arabic, where
uppercase and letter-spacing are meaningless); unmeasured figures render `—` via `.unmeasured`,
never a plausible-looking number; motion durations 150/300/600 ms with a single easing
(`cubic-bezier(.2,.8,.2,1)`); `prefers-reduced-motion` collapses all of it.

### 8.3 Routes & features

`/` Home (hero + headline results strip) · `/chat` bilingual streaming chat · `/evals` benchmark
+ judge dashboard · `/tokenizer` Fertility Lab (corpus-level detail behind the hero's sentence) · `/edge` live
edge-node telemetry · `/registry` artifact lineage. Global: language toggle (EN/AR) that flips
`<html dir lang>`, sovereign-mode badge (reads `/v1/models` meta), model picker.

### 8.4 3D scenes (`src/three/`) — the centerpiece

Shared: one `<Canvas>` per scene, `dpr={[1, 2]}`, `frameloop="demand"` except during active
animation, `<AdaptiveDpr>` + `PerformanceMonitor` from drei degrade quality before dropping
frames; postprocessing limited to subtle `Bloom` (luminanceThreshold ≈ 0.85) + `Vignette`;
every scene has a static `poster.webp` fallback (no WebGL / reduced-motion / mobile-low).

**(a) The Specimen — hero + working demo (signature; DOM, not WebGL — ADR-0005).**
`components/fertility/Specimen.tsx`. A real sentence (user-editable; defaults to a bilingual
banking sentence) is set **once, intact**, at display size, in the dual-script pairing — one text
node, so per-glyph font fallback puts Arabic in Ruqaa and Latin in Fraunces. Beneath it runs a
measured rule broken into one dash per token, coloured by script (paper for Arabic, pewter for
Latin); the gap between dashes is the cut. On tokenizer switch the rule re-cuts under unchanged
text and the dashes morph into place: Arabic words fall into four or five, English words stay
whole. That is the visual argument, and it is evidence rather than ambience.

**Never mark tokens by splitting the text into per-token elements.** Text shaping does not cross
element boundaries, so `<span>`-per-token severs Arabic's joins and renders `التوفير` as isolated
letterforms — a typographic lie about the input. Boundaries are measured with
`Range.getClientRects()` instead, which the browser returns already bidi-reordered (one rect per
visual run), so mixed-script RTL needs no special-casing. The rule's vertical placement is derived
from canvas font metrics — baseline position inside the line box plus the string's own ink descent
— not a tuned fraction, so it holds across the fluid scale and Ruqaa's deep descenders.

Beneath it, `TokenizerLedger.tsx` prices **all five tokenizers at once** (tokens · tokens/word ·
×cost, cheapest marked); selection only chooses which row the rule illustrates. The comparison is
a column you read, not a sequence you have to remember.

**FertilityField (3D) is the opt-in second reading**, collapsed by default: the same
`POST /v1/tokenize/fertility` segments drive glyph-particles (instanced quads sampling an MSDF
atlas built at startup — `lib/glyphAtlas.ts`; Arabic shaped in DOM first, then rasterized, so
ligatures stay correct) regrouping into token clusters via `useTokenClusters.ts`, cream for
Arabic and pewter for Latin. Interaction: drag to orbit (damped), scroll passes through.
Budget: ≤ 1,200 instanced glyphs, one draw call per script, custom shader (position lerp +
cluster color) — no per-glyph meshes.

**(b) PipelineOrbit — architecture as space (`/` section 2).**
Five glass panels (Data → QLoRA → Quantize → Eval → Edge) orbit a slowly-rotating core; drei
`ScrollControls` scrubs the camera along the arc; clicking a panel routes to its page. Panels
are `MeshTransmissionMaterial`-lite (or plain translucent standard material if GPU budget
complains); labels via drei `<Text>` (troika) in both scripts.

**(c) EdgeBoard — live telemetry (`/edge`).**
A low-poly edge board (single glTF ≤ 300 KB, draco-compressed, authored once) with emissive
heat responding to live watts from `/v1/telemetry/stream`; verdigris needle gauges (tok/s, °C, W)
are HTML overlays (drei `<Html>`) so numbers stay crisp and accessible. SSE hook `lib/sse.ts`
reconnects with backoff.

### 8.5 State & data

TanStack Query for all REST (staleTime tuned per resource; eval runs 60 s); zustand for
UI/tokenizer/3D-shared state only; generated client from OpenAPI (`just api-types` →
`src/lib/api/`); never hand-write fetch types.

### 8.6 Bilingual & bidi correctness (test-covered, non-negotiable)

- `dir` flips at `<html>`; components use **logical properties only** (`ms-*`, `pe-*`,
  `text-start`) — a Biome-assisted grep in CI fails on `ml-|mr-|pl-|pr-|text-left|text-right`.
- Chat messages get `dir="auto"` per message; mixed-script inline spans wrapped with
  `unicode-bidi: isolate`.
- **Streaming Arabic must not tear ligatures:** buffer SSE deltas and flush on grapheme
  boundaries via `Intl.Segmenter('ar', {granularity: 'grapheme'})` (`lib/bidi.ts`).
- Numerals: `Intl.NumberFormat(locale)`; a settings toggle for Eastern Arabic numerals
  (`ar-u-nu-arab` — the UAE/MSA Arabic-Indic digits ٠١٢٣; CLDR `arabext` is the
  Persian/Urdu set and is wrong here) in AR mode.
- Playwright captures RTL **and** LTR snapshots for every page, **served from
  `e2e/fixtures/api.ts`** so the baselines cover populated layouts rather than empty states.
- **Palette and typeface regressions get deterministic assertions, not pixel diffing**
  (`e2e/design-tokens.spec.ts`). Screenshot comparison scores each pixel against `threshold`
  before counting it toward `maxDiffPixelRatio`, so one dark ground sits within tolerance of
  another: the entire ADR-0005 palette change moved only 2 of 12 baselines. Tolerance is not the
  lever to tighten — baselines are authored on a dev machine and compared on an ubuntu runner, so
  the headroom absorbs font rasterisation. Assert computed style instead.
- **Language-scoped CSS uses `:lang()` on the element, never as a descendant combinator.**
  `:lang(ar) .font-display` also captures `lang="en"` children inside an Arabic page — that is
  what made the wordmark's Latin half fall back to a generic serif. `:lang()` already matches on
  inherited language, so the descendant form buys nothing and breaks mixed-script markup.

### 8.7 Frontend quality bars

Lighthouse (desktop): ≥ 90 on non-3D routes, ≥ 75 on `/` with hero; JS ≤ 350 KB gzip initial,
three.js chunk lazy-loaded per scene (`import()` + Suspense skeleton); a11y: visible focus,
`aria-live="polite"` on streaming message + token HUD, canvas has text alternative + skip link;
fonts subsetted (Latin + Arabic ranges) and self-hosted — `just verify-no-cdn` gate.

---

## 9. Infrastructure as Code

### 9.1 Terraform / OpenTofu (`infra/terraform`)

State: S3-compatible backend on MinIO with native lockfile (`use_lockfile = true`; TF ≥ 1.10 /
tofu ≥ 1.8). Envs `dev` and `prod` are thin compositions of modules; no resources at root.

| Module | Provisions | Notes |
|---|---|---|
| `gpu_train` | one spot GPU instance in **aws me-central-1** (type = `var.instance_type`, default g5.2xlarge — **verify regional availability before apply**), 200 GB gp3, cloud-init: NVIDIA driver, uv, repo clone, `just ml-setup` | includes a **CPU alarm auto-stop** (idle 30 min → stop) — the cost guard |
| `k3s_cluster` | on-prem nodes via SSH (or cloud VMs in dev): k3s server+agents, GPU node labeled `sanad.ai/gpu=true`, NVIDIA device plugin | kubeconfig exported to SOPS |
| `registry_minio_harbor` | MinIO (models, tfstate) + Harbor (images) via helm_release | Harbor project `sanad` with vuln-scan-on-push + cosign policy |
| `observability` | kube-prometheus-stack, Loki, dcgm-exporter, dashboards from `ops/dashboards` | installs the egress-zero PrometheusRule |
| `network` | VPC/subnets/SGs (cloud) or noop (on-prem) | SGs: API 443 only; vLLM never public |

```hcl
# envs/prod/main.tf — shape (excerpt)
module "gpu_train" {
  source        = "../../modules/gpu_train"
  region        = "me-central-1"          # data residency: training data never leaves UAE region
  instance_type = var.train_instance_type
  spot          = true
  auto_stop_min = 30
}
module "k3s"   { source = "../../modules/k3s_cluster"  nodes = var.onprem_nodes }
module "obs"   { source = "../../modules/observability" cluster = module.k3s }
```

### 9.2 Edge serving (compose `edge` profile — ADR-0004)

No config-management layer: the edge deployment is the compose `edge` profile (pinned
llama.cpp server image, GGUF mounted read-only, sha256-verified on sync from MinIO via
`mc mirror`). `just edge-sim` brings it up; `just bench-edge` records the efficiency numbers.
The former Ansible/Jetson provisioning path was removed by ADR-0004.

### 9.3 Helm charts (`infra/helm/charts`)

- `vllm`: GPU nodeSelector + `runtimeClassName: nvidia`, PVC `models` (RWO), initContainer
  `mc mirror` from MinIO, resources `nvidia.com/gpu: 1`, liveness `/health`, PodDisruptionBudget.
- `sanad-api`: HPA (CPU 70%), readiness `/readyz`, env from SOPS-decrypted Secret, ServiceMonitor.
- `sanad-web`: nginx serving `dist/`, CSP `default-src 'self'` header baked into nginx.conf.
- `eval-job`: a K8s **Job** template (GPU) that runs `run_lm_eval.sh` + judge harness, then POSTs
  reports to `/v1/eval/runs/{id}/ingest` — evals are jobs, not always-on services.
- `sovereign-guard`: default-deny egress NetworkPolicies for the namespace (DNS + intra-namespace
  allowed), plus the `SanadSovereignEgress` PrometheusRule: alert if
  `sum(rate(container_network_transmit_bytes_total{namespace="sanad",pod!~"sanad-web.*"}[5m]))`
  to non-cluster CIDRs > 0 for 10 m. **This alert firing = broken promise.**

### 9.4 Compose (dev & demo)

`docker-compose.yml` services: `postgres:17`, `redis:7`, `minio`, `mlflow`, `api` (reload),
`web` (vite dev), `prometheus`, `grafana`; profiles: `gpu` adds `vllm`, `edge` adds `llamacpp`
(x86 build for laptop demos), `trace` adds `langfuse`. `compose.sovereign.yml` overlays
`network_mode` restrictions + offline env vars for air-gapped demos on one box.

### 9.5 CI/CD (`.github/workflows`)

- **ci.yml** (PR): uv sync + ruff + mypy + pytest (both Python workspaces) · pnpm install +
  biome + tsc + vitest + playwright smoke (LTR+RTL) · `just data-gate` (license/manifest) ·
  docker build api/web → Trivy scan → Syft SBOM → cosign sign → push Harbor (on main) ·
  `just verify-no-cdn`.
- **eval.yml** (`workflow_dispatch`; GPU work runs on the local 4090 per ADR-0004): ingests
  the uploaded harness + judge + fertility report artifacts, posts summary comment, ingests to API. Contains
  the **regression gate**: fine-tuned must beat base by ≥ +5 pts on the domain eval and stay
  within −1 pt on ArabicMMLU (no catastrophic forgetting) — else red.
- **release.yml** (tag): helm package + push, tofu plan (manual apply gate), GitHub Release with
  manifest hashes.

---

## 10. Security & sovereignty checklist (audited per release)

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

```make
# ── setup ──────────────────────────────────────────────
setup:            # uv sync (ml, api) + pnpm install + pre-commit install
api-types:        # export OpenAPI → hey-api generate → src/lib/api/
# ── data / ml ──────────────────────────────────────────
data:             # ingest → normalize → langid → dedup → validate → MANIFEST.yaml
data-gate:        # license/provenance CI gate
train cfg="configs/train/qwen3-4b-qlora-dora.yaml":   # uv run train/sft.py --config {{cfg}}
merge cfg="configs/train/qwen3-4b-qlora-dora.yaml":   # adapters → merged-bf16 + manifest
quant-awq model="out/merged-bf16":    # llm-compressor recipe
quant-gguf model="out/merged-bf16":   # convert → imatrix → Q4_K_M
ppl-gate model:   # quality gate
eval model:       # run_lm_eval.sh {{model}}
judge run_id:     # 3C3H multi-judge + agreement.py
fertility:        # regenerate fertility.json
registry-push v:  # artifacts → MinIO + cosign
# ── app ────────────────────────────────────────────────
dev:              # docker compose up postgres redis minio mlflow + api reload + web vite
gpu:              # compose --profile gpu (adds vLLM)
edge-sim:         # compose --profile edge (x86 llama.cpp for laptop demo)
check:            # EVERYTHING a PR must pass locally (lint+type+test both stacks + data-gate + verify-no-cdn)
verify-no-cdn:    # grep dist/ for external origins
# ── infra ──────────────────────────────────────────────
tofu-plan env:    # cd infra/terraform/envs/{{env}} && tofu plan
tofu-apply env:
helm-deploy env:  # helmfile-style apply of charts with sops-decrypted values
bench-edge:       # local llama.cpp bench (ops/runbooks/edge-bench.md) → evals/reports/edge_bench.json
```

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

**Verified on Hugging Face 2026-07-25.** Pins now in the repo:

| Pin | Value | Consumed by |
|---|---|---|
| Qwen3-4B revision | `cdbee75f17c01a7cc42f958dc650907174af0554` | `configs/train/qwen3-4b-qlora-dora.yaml` (P2) |
| llama.cpp commit | `c0bc8591e8815c63cb01dd3f051a8b0df02501c9` (release `b10107`) | `configs/quant/gguf-q4km.yaml` (P3) |
| lm-eval commit | `6d642546f4688648fced259eb3302efd36ece5af` (`v0.4.12`) | `evals/harness/run_lm_eval.sh` (P4) |

`sft.py` enforces that `revision` is a 40-char lowercase commit sha — a branch or tag would let a
rerun train against different weights, so neither passes the gate.

**Two access prerequisites, both discovered at verification and neither automatable:**

- `meta-llama/Llama-3.2-3B-Instruct` is **`gated: manual`** — Meta approves each request by hand.
  Its tokenizer is one of the five in the fertility comparison (§5.4d), so `just fertility` cannot
  produce a complete table until that approval lands. Request it early; it is the long-lead item.
- `inceptionai/jais-family-6p7b-chat` is **`gated: auto`** — accept the terms once while online and
  the download proceeds; the sync needs an `HF_TOKEN` present.

**ALLaM moved orgs**: `ALLaM-AI/` → `humain-ai/`. Hugging Face serves a 307 for the old path, so a
browser follows it silently, but an offline mirror pass resolves ids literally and would fail. The
table and all four code references were corrected; treat this as the standing reason to re-verify
ids rather than trust them.

*Everything else above was current as of early 2026 — re-verify on Hugging Face at bootstrap time,
since newer checkpoints may exist.*

---
*End of CLAUDE.md — if you're Claude Code and you read this far: run `just --list`, pick the
current phase from §13, and open a small PR.*
