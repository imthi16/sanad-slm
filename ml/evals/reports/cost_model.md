# $/1M output tokens — cost model (§5.4e efficiency panel)

Every $/token figure quoted anywhere traces to this model. Numbers in `edge_bench.json` /
DCGM panels are measured; the formulas below turn them into cost.

## Inputs (fill per deployment; record alongside every quoted figure)

| Symbol | Meaning | Example |
|---|---|---|
| `P_avg` | mean device power during sustained generation (W) — RAPL (CPU) / DCGM (GPU) | CPU edge (i9-14900K, llama.cpp): ~65 W · RTX 4090: 320 W |
| `R` | sustained generation rate (tok/s), measured by `just bench-edge` / vLLM bench | CPU edge Q4_K_M: ~15–25 · vLLM AWQ: 1400 (batched) |
| `C_kwh` | electricity price ($/kWh), UAE commercial tariff | 0.10 |
| `H_cap` | hardware amortization ($/hour) = price ÷ (3 y × 8760 h × utilization) | workstation share attributable to serving: document the split used |

## Formulas

```
energy_cost_per_1M  = (P_avg / 1000) × (1e6 / R / 3600) × C_kwh          # $ electricity
amort_cost_per_1M   = H_cap × (1e6 / R / 3600)                            # $ hardware
total_$_per_1M_out  = energy_cost_per_1M + amort_cost_per_1M
```

## Reporting rules

- Always publish alongside the comparator's figure computed with the *same* formula (e.g. a
  72B on a rented A100 endpoint) — the efficiency delta is the headline, not the raw number.
- Batched-server numbers (vLLM) must state the concurrency used; single-stream edge numbers
  must state the platform label (`x86-local`) and thread count.
- Update the worked examples here whenever `edge_bench.json` is regenerated; quote by commit.
