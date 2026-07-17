# ADR-0004: Drop the Jetson hardware target; single-workstation compute (RTX 4090)

Date: 2026-07-08 · Status: accepted · Amends: ADR-0003 (items 1, 2, 4)

## Context

The project owner's machine is an i9-14900K (24C/32T) workstation with an RTX 4090 (24 GB) —
exactly the "single 24 GB GPU" the training recipe was designed for. No Jetson board exists or
will be purchased (zero-cost constraint, ADR-0003). Keeping Jetson-specific provisioning code
(Ansible role, JetPack container build, tegrastats exporter, systemd units) means maintaining
artifacts that can never be exercised — worse for a portfolio than a smaller true story.

## Decisions

1. **Jetson hardware target removed.** Deleted: `infra/ansible/` (existed solely for Jetson
   provisioning), `serving/llamacpp/Dockerfile.jetson`, the systemd unit, the jetson-bench
   runbook, and the ansible-lint CI step. ADR-0002 §5 (tegrastats exporter) is historical
   record; the exporter is gone.
2. **The edge story stays — as commodity-CPU serving.** The dual-artifact claim becomes:
   *one model, two deployment shapes* — vLLM + AWQ on the GPU, llama.cpp + GGUF Q4_K_M on
   CPU-only commodity hardware. `SANAD_MODE=edge`, the compose `edge` profile
   (`ghcr.io/ggml-org/llama.cpp:server`, x86), the Edge dashboard page, EdgeBoard scene, and
   telemetry SSE all remain, reworded from "Jetson" to "edge node". Efficiency numbers carry
   `platform: x86-local` (prime directive 5).
3. **`just bench-edge` replaces `bench-jetson`.** New runbook + script
   (`ops/runbooks/edge-bench.{md,sh}`): llama-bench in the pinned container, CPU watts via
   Intel RAPL when readable, output to `ml/evals/reports/edge_bench.json` (same consumer).
4. **Training runs locally on the RTX 4090** — amends ADR-0003(1): no cloud burst, no Kaggle
   dependency. bf16 is native (Ada), so the canonical train config applies unchanged (no fp16
   variant needed). Kaggle/Colab demoted to overflow/fallback only. Cost stays $0 (plus
   electricity, logged via the cost model).
5. **Sovereign judges run locally too** — amends ADR-0003(4): Falcon-H1-7B + ALLaM-7B served
   quantized (AWQ) sequentially on the 4090; no Kaggle session juggling.
6. **The `gpu_train` Terraform module stays plan-only** (unchanged from ADR-0003) — it remains
   a reviewable IaC artifact, now clearly labeled as never-applied.

## Consequences

- The README/hero claim changes from "…and on a Jetson Orin at the edge" to "…and on
  commodity CPU-only hardware at the edge" — a claim we can actually demonstrate live.
- P3 acceptance becomes: both quant gates pass; `bench-edge` numbers (tok/s, watts where
  readable) recorded from this workstation.
- One machine is now a single point of failure for the whole pipeline; mitigated by MinIO
  artifact pushes and the HF Hub mirror (ADR-0003 item 6).
