# SANAD command surface — the ONLY entry point (CLAUDE.md §12).
# `just --list` for help. Recipes are thin; logic lives in the workspaces.

set shell := ["bash", "-euo", "pipefail", "-c"]

ML := "ml"
API := "apps/api"
WEB := "apps/web"
COMPOSE := "infra/compose/docker-compose.yml"
# Where `just sync-tokenizers` puts the tokenizer.json files. The API's own default
# (/models/tokenizers) is the *container* path the Helm initContainer mirrors into, so a locally
# run uvicorn has to be pointed here or /v1/tokenize/fertility 503s and the hero stays empty.
TOKENIZERS := justfile_directory() / "ml/out/tokenizers"

default:
    @just --list

# ── setup ──────────────────────────────────────────────

# uv sync (ml, api) + pnpm install + pre-commit install
setup:
    cd {{ML}} && uv sync
    cd {{API}} && uv sync
    cd {{WEB}} && pnpm install
    uvx pre-commit install

# export OpenAPI → hey-api generate → apps/web/src/lib/api/ (generated: never hand-edit)
api-types:
    cd {{API}} && uv run python -c "import json; from sanad_api.main import app; print(json.dumps(app.openapi()))" > ../../{{WEB}}/openapi.json
    cd {{WEB}} && pnpm exec openapi-ts -i openapi.json -o src/lib/api && rm openapi.json

# ── data / ml ──────────────────────────────────────────

# ingest (CIDAR + own bank pairs) → normalize → langid → dedup → split → calib → MANIFEST.yaml
data:
    cd {{ML}} && uv run python data/scripts/ingest_cidar.py
    # curate_bank emits data/raw/bank_records.jsonl, which normalize globs next. Without this
    # step the whole domain corpus — the entire point of the fine-tune — is silently absent.
    cd {{ML}} && uv run python data/scripts/curate_bank.py --emit
    cd {{ML}} && uv run python data/scripts/normalize.py data/raw data/processed
    cd {{ML}} && uv run python data/scripts/langid.py data/processed
    cd {{ML}} && uv run python data/scripts/dedup.py data/processed
    cd {{ML}} && uv run python data/scripts/split.py
    cd {{ML}} && uv run python data/scripts/calib.py
    cd {{ML}} && uv run python data/scripts/manifest.py build

# license/provenance CI gate (fails on non-commercial records in a commercial manifest)
data-gate:
    cd {{ML}} && uv run python data/scripts/manifest.py gate --profile commercial

# MLflow tracking UI on http://localhost:5000 — watch loss/VRAM/cost during a run
mlflow-ui port="5000":
    cd {{ML}} && uv run mlflow ui --host 127.0.0.1 --port {{port}}

# verify GPU, extras, pins and data BEFORE a multi-hour run (train/preflight.py)
preflight cfg="configs/train/qwen3-4b-qlora-dora.yaml":
    cd {{ML}} && uv run python train/preflight.py --config {{cfg}}

train cfg="configs/train/qwen3-4b-qlora-dora.yaml":
    cd {{ML}} && uv run python train/sft.py --config {{cfg}}

# adapters → merged-bf16 + lineage manifest
merge cfg="configs/train/qwen3-4b-qlora-dora.yaml":
    cd {{ML}} && uv run python train/merge.py --config {{cfg}}

# Run after `just train`, then force-add the report: mlflow.db is not in git, so without this the
# VRAM/wall-time/loss figures trace to nothing a reader can check (prime directive 6).
# MLflow run → committable, hashable metrics report in evals/reports/
export-metrics run_id db="mlflow.db":
    cd {{ML}} && uv run python train/export_metrics.py --tracking-db {{db}} --run-id {{run_id}}

# llm-compressor AWQ W4A16 (compressed-tensors, vLLM-native)
quant-awq model="out/merged-bf16":
    cd {{ML}} && uv run python quantize/awq.py --model {{model}} --recipe configs/quant/awq-w4a16.yaml \
        --calib data/processed/calib_bilingual_512.jsonl

# convert → bilingual imatrix → GGUF Q4_K_M
quant-gguf model="out/merged-bf16":
    cd {{ML}} && bash quantize/gguf.sh {{model}}

# quantization quality gate: ΔPPL ≤3% (AWQ) / ≤5% (GGUF), ArabicMMLU drop ≤1.0 pt
ppl-gate model:
    cd {{ML}} && uv run python quantize/ppl_gate.py --model {{model}}

# pinned lm-evaluation-harness across the benchmark matrix
eval model:
    cd {{ML}} && bash evals/harness/run_lm_eval.sh {{model}}

# 3C3H multi-judge + Krippendorff/κ agreement stats
judge run_id:
    cd {{ML}} && uv run python evals/judge/run_judges.py --run-id {{run_id}}
    cd {{ML}} && uv run python evals/judge/agreement.py --run-id {{run_id}}

# Run before `just dev` or the Specimen hero has nothing to measure. Three of five land without
# credentials; the two gated repos need terms accepted once (§15) and render as `—` until then.
# fetch the five tokenizer.json files fertility needs (tokenizers only, never weights)
sync-tokenizers:
    cd {{ML}} && uv run python evals/fertility/sync_tokenizers.py

# corpus-level fertility.json (consumed by API + Evals page) — needs the three frozen corpora
fertility:
    cd {{ML}} && uv run python evals/fertility/measure.py --out evals/reports/fertility.json

# Measures the specimen sentence through the API's own fertility service, then drives the built app
# and captures the re-cut. Needs `just sync-tokenizers` + Pillow; not part of `just check`.
# re-record the README hero GIF from real tokenizer output
capture-specimen:
    cd {{API}} && uv run python scripts/measure_specimen.py --tokenizers-dir "{{TOKENIZERS}}"
    cd {{WEB}} && pnpm exec playwright test --config playwright.capture.config.ts

# artifacts → MinIO + cosign-signed manifest
registry-push v:
    cd {{ML}} && uv run python registry/push.py --version {{v}}

# ── app ────────────────────────────────────────────────

# dev stack: postgres redis minio mlflow prometheus grafana + api reload + web vite
dev:
    docker compose -f {{COMPOSE}} up -d postgres redis minio mlflow prometheus grafana
    (cd {{API}} && SANAD_TOKENIZERS_DIR="${SANAD_TOKENIZERS_DIR:-{{TOKENIZERS}}}" \
        uv run uvicorn sanad_api.main:app --reload --port 8000) & \
    (cd {{WEB}} && pnpm dev) & \
    wait

# compose --profile gpu (adds vLLM)
gpu:
    docker compose -f {{COMPOSE}} --profile gpu up -d

# compose --profile edge (x86 llama.cpp for laptop demos)
edge-sim:
    docker compose -f {{COMPOSE}} --profile edge up -d

# EVERYTHING a PR must pass locally (mirrors ci.yml)
check:
    cd {{ML}} && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -q
    cd {{API}} && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q --cov=src/sanad_api/services --cov=src/sanad_api/routers --cov-fail-under=80
    cd {{WEB}} && pnpm exec biome check . && pnpm exec tsc --noEmit && pnpm exec vitest --run && node scripts/check-i18n-sync.mjs
    just data-gate
    just verify-no-cdn

# scan built web dist/ for external origins — sovereign gate (build first if missing).
# HTML/CSS: zero tolerance; JS: justified allowlist of inert strings (see the script).
# execute the §10 sovereignty checklist (no cluster needed; reports what still needs one)
sovereign-audit:
    python3 ops/sovereign_audit.py

# verify a signature before trusting an artifact: `just verify-artifact image <ref>`
verify-artifact kind ref:
    bash ops/verify-artifacts.sh {{kind}} {{ref}}

verify-no-cdn:
    @test -d {{WEB}}/dist || (cd {{WEB}} && pnpm build)
    cd {{WEB}} && node scripts/verify-no-cdn.mjs dist

# ── infra ──────────────────────────────────────────────

tofu-plan env:
    cd infra/terraform/envs/{{env}} && tofu init -backend=false && tofu validate && tofu plan

tofu-apply env:
    cd infra/terraform/envs/{{env}} && tofu apply

# sops-decrypted values → helm upgrade --install of all charts
helm-deploy env:
    bash infra/helm/deploy.sh {{env}}

# local llama.cpp bench (ops/runbooks/edge-bench.md), writes evals/reports/edge_bench.json
bench-edge:
    bash ops/runbooks/edge-bench.sh
