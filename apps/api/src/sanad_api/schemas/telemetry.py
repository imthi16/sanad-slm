"""Edge/GPU telemetry shapes (§7.2 /v1/telemetry/stream, EdgeBoard scene)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class TelemetrySnapshot(BaseModel):
    source: str  # e.g. edge-01 | gpu-node-0
    ts: dt.datetime
    watts: float | None = None
    gpu_util_pct: float | None = None
    temp_c: float | None = None
    tokens_per_second: float | None = None
    mem_used_gb: float | None = None


class ModelInfo(BaseModel):
    alias: str
    upstream_kind: str  # vllm | llamacpp
    healthy: bool
    quant_format: str | None = None  # awq-w4a16 | gguf-q4_k_m | bf16
    license: str | None = None
    sovereign: bool = True
