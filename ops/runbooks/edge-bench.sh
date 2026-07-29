#!/usr/bin/env bash
# Edge bench (ops/runbooks/edge-bench.md → `just bench-edge`): llama-bench on the local
# GGUF, CPU-only, plus RAPL package watts when readable. Writes ml/evals/reports/edge_bench.json.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
THREADS="${SANAD_BENCH_THREADS:-$(nproc)}"
IMAGE="${SANAD_LLAMACPP_BENCH_IMAGE:-ghcr.io/ggml-org/llama.cpp:full}"
OUT="$REPO_ROOT/ml/evals/reports/edge_bench.json"
RAPL="/sys/class/powercap/intel-rapl:0/energy_uj"

# Look where the pipeline actually writes first. The compose path is a *deployment* mount that
# only exists after `mc mirror`; defaulting to it made `just bench-edge` fail on 2026-07-28 with
# "GGUF not found" immediately after gguf.sh had written a perfectly good artifact to ml/out/.
if [[ -n "${SANAD_GGUF_PATH:-}" ]]; then
    MODEL="$SANAD_GGUF_PATH"
elif [[ -f "$REPO_ROOT/ml/out/sanad-Q4_K_M.gguf" ]]; then
    MODEL="$REPO_ROOT/ml/out/sanad-Q4_K_M.gguf"
else
    MODEL="$REPO_ROOT/infra/compose/models/sanad-Q4_K_M.gguf"
fi
[[ -f "$MODEL" ]] || { echo "FATAL: GGUF not found at $MODEL (set SANAD_GGUF_PATH)" >&2; exit 1; }

# A native llama-bench beats the container here. The edge target is a CPU-only box, and the one
# this project actually runs on has neither Docker nor sudo — benchmarking through a container we
# cannot start would make the edge claim unmeasurable on the very hardware it describes.
# SANAD_LLAMA_BIN, then anything on PATH, then the build tree gguf.sh produces, then Docker.
BENCH_BIN=""
for cand in "${SANAD_LLAMA_BIN:-}" "$(command -v llama-bench || true)" \
            "$REPO_ROOT/ml/out/llama.cpp/build/bin/llama-bench"; do
    [[ -n "$cand" && -x "$cand" ]] && { BENCH_BIN="$cand"; break; }
done

rapl_read() { [[ -r "$RAPL" ]] && cat "$RAPL" || echo ""; }

E0=$(rapl_read); T0=$(date +%s.%N)
if [[ -n "$BENCH_BIN" ]]; then
    RUNNER="native:$BENCH_BIN"
    echo "→ native llama-bench: $BENCH_BIN (threads=$THREADS)" >&2
    BENCH_JSON=$(LD_LIBRARY_PATH="$(dirname "$BENCH_BIN"):${LD_LIBRARY_PATH:-}" \
        "$BENCH_BIN" -m "$MODEL" -t "$THREADS" -p 512 -n 128 -o json)
elif command -v docker >/dev/null 2>&1; then
    RUNNER="docker:$IMAGE"
    echo "→ no native llama-bench; falling back to $IMAGE" >&2
    BENCH_JSON=$(docker run --rm -v "$(dirname "$MODEL"):/models:ro" "$IMAGE" \
        --bench -m "/models/$(basename "$MODEL")" -t "$THREADS" -p 512 -n 128 -o json 2>/dev/null) \
        || BENCH_JSON=$(docker run --rm --entrypoint /app/llama-bench -v "$(dirname "$MODEL"):/models:ro" \
        "$IMAGE" -m "/models/$(basename "$MODEL")" -t "$THREADS" -p 512 -n 128 -o json)
else
    echo "FATAL: no llama-bench binary and no docker. Set SANAD_LLAMA_BIN to a llama-bench" >&2
    echo "       from the pinned release, or build it via quantize/gguf.sh." >&2
    exit 1
fi
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
    "runner": "$RUNNER",
    "pp_tps": tps("pp"),
    "tg_tps": tps("tg"),
    "watts_avg": $WATTS,
    "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
json.dump(report, open(sys.argv[1], "w"), indent=2)
print(json.dumps(report, indent=2))
PY
echo "wrote $OUT"
