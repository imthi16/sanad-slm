#!/usr/bin/env bash
# Edge bench (ops/runbooks/edge-bench.md → `just bench-edge`): llama-bench on the local
# GGUF, CPU-only, plus RAPL package watts when readable. Writes ml/evals/reports/edge_bench.json.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="${SANAD_GGUF_PATH:-$REPO_ROOT/infra/compose/models/sanad-Q4_K_M.gguf}"
THREADS="${SANAD_BENCH_THREADS:-$(nproc)}"
IMAGE="${SANAD_LLAMACPP_BENCH_IMAGE:-ghcr.io/ggml-org/llama.cpp:full}"
OUT="$REPO_ROOT/ml/evals/reports/edge_bench.json"
RAPL="/sys/class/powercap/intel-rapl:0/energy_uj"

[[ -f "$MODEL" ]] || { echo "FATAL: GGUF not found at $MODEL (set SANAD_GGUF_PATH)" >&2; exit 1; }

rapl_read() { [[ -r "$RAPL" ]] && cat "$RAPL" || echo ""; }

E0=$(rapl_read); T0=$(date +%s.%N)
BENCH_JSON=$(docker run --rm -v "$(dirname "$MODEL"):/models:ro" "$IMAGE" \
    --bench -m "/models/$(basename "$MODEL")" -t "$THREADS" -p 512 -n 128 -o json 2>/dev/null) \
    || BENCH_JSON=$(docker run --rm --entrypoint /app/llama-bench -v "$(dirname "$MODEL"):/models:ro" \
    "$IMAGE" -m "/models/$(basename "$MODEL")" -t "$THREADS" -p 512 -n 128 -o json)
E1=$(rapl_read); T1=$(date +%s.%N)

WATTS=null
if [[ -n "$E0" && -n "$E1" ]]; then
    # RAPL counter is µJ and wraps; only report on a monotonic window
    WATTS=$(python3 -c "e=($E1-$E0)/1e6; t=$T1-$T0; print(round(e/t,1) if e>0 and t>0 else 'null')")
fi

python3 - "$OUT" <<PY
import json, subprocess, sys, datetime
bench = json.loads('''$BENCH_JSON''')
rows = {r.get("test",""): r for r in bench} if isinstance(bench, list) else {}
def tps(prefix):
    for k, r in rows.items():
        if k.startswith(prefix):
            return round(r.get("avg_ts", 0.0), 1)
    return None
report = {
    "platform": "x86-local",
    "cpu": subprocess.run(["sh","-c","lscpu | awk -F': +' '/Model name/{print \$2; exit}'"],
                          capture_output=True, text=True).stdout.strip(),
    "threads": $THREADS,
    "model": "$(basename "$MODEL")",
    "image": "$IMAGE",
    "pp_tps": tps("pp"),
    "tg_tps": tps("tg"),
    "watts_avg": $WATTS,
    "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
json.dump(report, open(sys.argv[1], "w"), indent=2)
print(json.dumps(report, indent=2))
PY
echo "wrote $OUT"
