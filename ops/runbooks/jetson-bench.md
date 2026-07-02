# Runbook: Jetson benchmark (`just bench-jetson <host>`)

Published Jetson numbers vary widely by JetPack version, llama.cpp commit, and power mode —
**never quote a number without the triple recorded next to it** (§6.2). This runbook is
automated by `roles/jetson_edge/files/bench.sh` (Ansible `--tags bench`); the manual steps
below are what it does, for when you need to debug.

## Preconditions

- Board provisioned (`just edge-provision`), `llama-server` active
  (`systemctl status llama-server`), model sha256-verified.
- Power mode set intentionally: `sudo nvpmodel -q` — record it. MAXN vs 15W changes tok/s
  by ~2×.
- Board idle otherwise (no browser, no compile jobs); fan profile default.

## Steps

1. **Warm-up** (first request pays mmap+graph build):
   `curl -s localhost:8080/v1/chat/completions -d '{"messages":[{"role":"user","content":"مرحبا"}],"max_tokens":32}' -H 'Content-Type: application/json' >/dev/null`
2. **Single-stream**: 256-token Arabic completion, temperature 0. Record
   `usage.completion_tokens / wall_seconds`.
3. **Parallel=2**: same prompt twice concurrently (matches `--parallel 2` serving config).
4. **Power**: run `tegrastats --interval 500` for the duration; average the `VDD_IN` /
   `VIN_SYS` mW column → watts.
5. **Write** `evals/reports/edge_bench.json`:

```json
{
  "board": "NVIDIA Orin Nano 8GB",
  "jetpack": "R36.x",
  "llamacpp_rev": "<pinned sha>",
  "power_mode": "MAXN",
  "measured_at": "2026-…",
  "cases": [
    {"case": "single-stream", "tokens_per_second": 0.0, "avg_watts": 0.0},
    {"case": "parallel-2", "tokens_per_second": 0.0, "avg_watts": 0.0}
  ]
}
```

6. **Ingest**: POST to `/v1/eval/runs/edge-bench-<date>/ingest` (bench.sh does this) so the
   Evals page and the README efficiency panel read from the same source.
7. **Cost**: feed watts + tok/s into `ml/evals/reports/cost_model.md` formulas for the
   $/1M-token figure.

## Expected envelope (sanity check, NOT quotable)

Orin Nano 8 GB, 4B Q4_K_M: weights ~2.5–3 GB + KV 0.5–1.5 GB; ~20–30 tok/s single-stream.
Outside that range → check `-ngl 99` actually offloaded (look for `offloaded 99/99 layers`
in the server log), power mode, and thermals (`sanad_edge_temp_c` < 70 °C sustained).
