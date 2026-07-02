#!/usr/bin/env bash
# Jetson benchmark (§6.2, runbook ops/runbooks/jetson-bench.md) — measures single-stream and
# parallel generation against the local llama-server, captures watts via tegrastats, and
# writes edge_bench.json for ingestion. Numbers vary by JetPack/llama.cpp/power mode: the
# JSON records all three.
set -euo pipefail

API_URL="${1:-http://localhost:8000}"
LLAMA="http://127.0.0.1:8080"
OUT=/tmp/edge_bench.json
PROMPT='اشرح متطلبات اعرف عميلك لفتح حساب مصرفي جديد في دولة الإمارات.'

power_mode=$(nvpmodel -q 2>/dev/null | head -1 || echo unknown)
jetpack=$(head -1 /etc/nv_tegra_release 2>/dev/null || echo unknown)

run_case() {
    local parallel=$1 label=$2
    tegrastats --interval 500 > /tmp/tegra_bench.log &
    local tpid=$!
    local t0=$(date +%s.%N)
    local pids=()
    for i in $(seq 1 "$parallel"); do
        curl -s "$LLAMA/v1/chat/completions" -H 'Content-Type: application/json' -d "{
            \"model\": \"sanad-bank-gguf\",
            \"messages\": [{\"role\": \"user\", \"content\": \"$PROMPT\"}],
            \"max_tokens\": 256, \"temperature\": 0
        }" > "/tmp/bench_out_$i.json" &
        pids+=($!)
    done
    wait "${pids[@]}"
    kill $tpid 2>/dev/null || true
    local t1=$(date +%s.%N)
    local total_tokens=$(python3 - <<'PY'
import glob, json
t = 0
for f in glob.glob("/tmp/bench_out_*.json"):
    try:
        t += json.load(open(f)).get("usage", {}).get("completion_tokens", 0)
    except Exception:
        pass
print(t)
PY
)
    local watts=$(grep -oP '(?:VDD_IN|VIN_SYS) \K\d+' /tmp/tegra_bench.log | \
        python3 -c 'import sys; v=[int(x) for x in sys.stdin]; print(round(sum(v)/len(v)/1000,2) if v else 0)')
    local secs=$(python3 -c "print(round($t1-$t0,2))")
    echo "{\"case\": \"$label\", \"parallel\": $parallel, \"completion_tokens\": $total_tokens, \"seconds\": $secs, \"tokens_per_second\": $(python3 -c "print(round($total_tokens/$secs,2) if $secs else 0)"), \"avg_watts\": $watts}"
    rm -f /tmp/bench_out_*.json /tmp/tegra_bench.log
}

single=$(run_case 1 single-stream)
dual=$(run_case 2 parallel-2)

cat > "$OUT" <<EOF
{
  "board": "$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo unknown)",
  "jetpack": "$jetpack",
  "power_mode": "$power_mode",
  "measured_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "cases": [$single, $dual]
}
EOF
echo "✓ wrote $OUT — copy into ml/evals/reports/edge_bench.json and ingest"
curl -s -X POST "$API_URL/v1/eval/runs/edge-bench-$(date +%Y%m%d)/ingest" \
    -H "Authorization: Bearer ${SANAD_SERVICE_TOKEN:-}" \
    -H 'Content-Type: application/json' \
    -d "{\"run_id\": \"edge-bench-$(date +%Y%m%d)\", \"reports\": {\"efficiency\": $(python3 -c "
import json
d = json.load(open('$OUT'))
c = d['cases'][0]
print(json.dumps({'tokens_per_second': c['tokens_per_second'], 'watts': c['avg_watts']}))
")}}" || echo "(API ingest skipped)"
