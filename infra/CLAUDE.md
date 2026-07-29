# CLAUDE.md — `infra/` · Infrastructure as Code

> Loads when Claude works under `infra/`. The root [`CLAUDE.md`](../CLAUDE.md) holds the prime
> directives — including **prime directive 1, sovereignty is a build mode** — and the §10 sovereignty
> checklist. Read it first; it wins on conflict.

## 9.1 Terraform / OpenTofu (`infra/terraform`)

OpenTofu-compatible HCL (works on Terraform ≥ 1.10 too). State: S3-compatible backend on MinIO with
native lockfile (`use_lockfile = true`; TF ≥ 1.10 / tofu ≥ 1.8 — **no DynamoDB**). Envs `dev` and
`prod` are thin compositions of modules; **no resources at root**.

| Module | Provisions | Notes |
|---|---|---|
| `gpu_train` | one spot GPU instance in **aws me-central-1** (type = `var.instance_type`, default g5.2xlarge — **verify regional availability before apply**), 200 GB gp3, cloud-init: NVIDIA driver, uv, repo clone, `just ml-setup` | includes a **CPU alarm auto-stop** (idle 30 min → stop) — the cost guard |
| `k3s_cluster` | on-prem nodes via SSH (or cloud VMs in dev): k3s server+agents, GPU node labeled `sanad.ai/gpu=true`, NVIDIA device plugin | kubeconfig exported to SOPS |
| `registry_minio_harbor` | MinIO (models, tfstate) + Harbor (images) via helm_release | Harbor project `sanad` with vuln-scan-on-push + cosign policy |
| `observability` | kube-prometheus-stack, Loki, dcgm-exporter, dashboards from `ops/dashboards` | installs the egress-zero PrometheusRule |
| `network` | VPC/subnets/SGs (cloud) or noop (on-prem) | SGs: API 443 only; vLLM never public |

**`gpu_train` is a plan-only artifact and is never applied** (ADR-0003/0004): training runs on the
local RTX 4090. The module stays in-repo as reviewable, CI-validated IaC (`tofu validate`, tflint) —
same for the paid-infra paths in `envs/prod`. Budget lines in reports read "$0 (local compute)".
`envs/prod/main.tf` pins `region = "me-central-1"` for data residency: training data never leaves
the UAE region.

## 9.2 Edge serving (compose `edge` profile — ADR-0004)

No config-management layer: the edge deployment is the compose `edge` profile (pinned
llama.cpp server image, GGUF mounted read-only, sha256-verified on sync from MinIO via
`mc mirror`). `just edge-sim` brings it up; `just bench-edge` records the efficiency numbers.
The former Ansible/Jetson provisioning path was removed by ADR-0004.

## 9.3 Helm charts (`infra/helm/charts`)

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

## 9.4 Compose (dev & demo)

`docker-compose.yml` services: `postgres:17`, `redis:7`, `minio`, `mlflow`, `api` (reload),
`web` (vite dev), `prometheus`, `grafana`; profiles: `gpu` adds `vllm`, `edge` adds `llamacpp`
(x86 build for laptop demos), `trace` adds `langfuse`. `compose.sovereign.yml` overlays
`network_mode` restrictions + offline env vars for air-gapped demos on one box.

`.env` files are **never** committed; `infra/compose/.env.example` documents every variable. Real
secrets live in `secrets/*.sops.yaml` (age recipients in `.sops.yaml`).

## 9.5 CI/CD (`.github/workflows`)

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

CI is GitHub Actions free tier on a public repo; there is **no self-hosted GPU runner**, which is why
`eval.yml` is dispatch-only and ingests locally produced reports.
