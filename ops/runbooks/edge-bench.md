# Edge bench — llama.cpp GGUF on the local workstation

Replaces the retired Jetson runbook (ADR-0004): the edge target is now the GGUF artifact
served by llama.cpp on commodity x86 — demonstrated on the project workstation
(i9-14900K, 24C/32T). Numbers are always labeled `platform: x86-local`; they are **never**
presented as embedded-board numbers (prime directive 5).

## What it measures

| Metric | How |
|---|---|
| prompt tok/s (`pp_tps`) / gen tok/s (`tg_tps`) | `llama-bench` (pp512 / tg128), CPU-only, in the pinned llama.cpp container |
| package watts (`watts_avg`) | Intel RAPL (`/sys/class/powercap/intel-rapl:0/energy_uj`) sampled around the run; `null` if unreadable (needs root on most kernels) |
| context | model file, quant, thread count, llama.cpp image digest, timestamp |

## Run

```bash
just bench-edge                       # uses SANAD_GGUF_PATH or infra/compose/models/sanad-Q4_K_M.gguf
sudo -E just bench-edge               # same, with RAPL watts
```

Output: `ml/evals/reports/edge_bench.json` — ingested by the efficiency panel (§5.4e) and
quoted in README/paper only by hash (working agreement 6).

Re-run and re-record whenever the GGUF artifact, llama.cpp image, or power profile changes.
