#!/usr/bin/env python3
"""tegrastats → Prometheus exporter (§6.2, §9.2).

Parses `tegrastats` output into gauges:
    sanad_edge_watts · sanad_edge_gpu_util · sanad_edge_temp_c · sanad_edge_mem_used_gb
and scrapes llama-server /metrics for tok/s. Optionally forwards snapshots to the SANAD API
(/v1/telemetry/ingest, SANAD_SERVICE_TOKEN) so the EdgeBoard scene gets live SSE frames.

Stdlib + prometheus_client only — this must run on a bare JetPack image.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import threading
import time
import urllib.request

from prometheus_client import Gauge, start_http_server

WATTS = Gauge("sanad_edge_watts", "board power draw (W)", ["source"])
GPU_UTIL = Gauge("sanad_edge_gpu_util", "GPU utilization (%)", ["source"])
TEMP_C = Gauge("sanad_edge_temp_c", "SoC temperature (°C)", ["source"])
MEM_GB = Gauge("sanad_edge_mem_used_gb", "RAM used (GB)", ["source"])
TOKS = Gauge("sanad_edge_tokens_per_second", "llama-server generation rate", ["source"])

# tegrastats line fragments across JetPack 5/6 variants
RAM_RE = re.compile(r"RAM (\d+)/(\d+)MB")
GPU_RE = re.compile(r"GR3D_FREQ (\d+)%")
TEMP_RE = re.compile(r"(?:tj|CPU|SOC0)@([\d.]+)C")
# power: VDD_IN or VIN_SYS 5000mW/5100mW style
POWER_RE = re.compile(r"(?:VDD_IN|VIN_SYS|POM_5V_IN) (\d+)mW")


def parse_line(line: str) -> dict[str, float | None]:
    ram = RAM_RE.search(line)
    gpu = GPU_RE.search(line)
    temp = TEMP_RE.search(line)
    power = POWER_RE.search(line)
    return {
        "mem_used_gb": round(int(ram.group(1)) / 1024, 2) if ram else None,
        "gpu_util_pct": float(gpu.group(1)) if gpu else None,
        "temp_c": float(temp.group(1)) if temp else None,
        "watts": round(int(power.group(1)) / 1000, 2) if power else None,
    }


def scrape_llama_toks(url: str) -> float | None:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            for line in r.read().decode().splitlines():
                # llama.cpp server exposes predicted tokens/sec
                if line.startswith("llamacpp:predicted_tokens_seconds") and not line.startswith("#"):
                    return float(line.rsplit(" ", 1)[-1])
    except Exception:
        return None
    return None


def forward_to_api(source: str, snapshot: dict[str, float | None]) -> None:
    api = os.environ.get("SANAD_API_URL")
    token = os.environ.get("SANAD_SERVICE_TOKEN")
    if not api or not token:
        return
    body = json.dumps({
        "source": source,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **snapshot,
    }).encode()
    req = urllib.request.Request(
        f"{api}/v1/telemetry/ingest",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass  # telemetry forwarding is best-effort; Prometheus scrape is the source of truth


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=9109)
    ap.add_argument("--source", default=os.uname().nodename)
    ap.add_argument("--interval", type=int, default=2000, help="tegrastats interval ms")
    args = ap.parse_args()

    start_http_server(args.port)
    llama_url = os.environ.get("LLAMA_METRICS_URL", "http://127.0.0.1:8080/metrics")

    def llama_loop() -> None:
        while True:
            toks = scrape_llama_toks(llama_url)
            if toks is not None:
                TOKS.labels(args.source).set(toks)
            time.sleep(5)

    threading.Thread(target=llama_loop, daemon=True).start()

    proc = subprocess.Popen(
        ["tegrastats", "--interval", str(args.interval)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    last_forward = 0.0
    for line in proc.stdout:
        snap = parse_line(line)
        if snap["watts"] is not None:
            WATTS.labels(args.source).set(snap["watts"])
        if snap["gpu_util_pct"] is not None:
            GPU_UTIL.labels(args.source).set(snap["gpu_util_pct"])
        if snap["temp_c"] is not None:
            TEMP_C.labels(args.source).set(snap["temp_c"])
        if snap["mem_used_gb"] is not None:
            MEM_GB.labels(args.source).set(snap["mem_used_gb"])
        now = time.monotonic()
        if now - last_forward >= 2.0:
            snap["tokens_per_second"] = scrape_llama_toks(llama_url)
            forward_to_api(args.source, snap)
            last_forward = now


if __name__ == "__main__":
    main()
