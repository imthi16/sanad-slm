# CLAUDE.md — `serving/` · Serving layer

> Loads when Claude works under `serving/`. The root [`CLAUDE.md`](../CLAUDE.md) holds the prime
> directives and the mode matrix (`dev` / `sovereign` / `edge`) — read it first; it wins on conflict.

## 6.1 vLLM (sovereign GPU server)

`serving/vllm/entrypoint.sh` (values templated by Helm/compose):

```bash
exec vllm serve /models/sanad-qwen3-4b-bank/awq-w4a16 \
  --served-model-name sanad-bank-awq \
  --max-model-len 8192 --gpu-memory-utilization 0.90 \
  --enable-prefix-caching --disable-log-requests \
  --host 0.0.0.0 --port 8000
```

Notes: model dir is a read-only PVC synced from MinIO by an initContainer (`mc mirror`);
quantization is auto-detected from the compressed-tensors checkpoint — don't pass legacy
`--quantization awq` flags unless vLLM asks; probe `/health`; one model per pod (HPA on
`num_requests_waiting`).

## 6.2 llama.cpp (CPU edge — ADR-0004)

- Image: `ghcr.io/ggml-org/llama.cpp:server` (pin a digest before P3), CPU-only x86; launched
  by the compose `edge` profile or `serving/llamacpp/run.sh`.
- Run: `llama-server -m /models/sanad-Q4_K_M.gguf -c 4096 --host 0.0.0.0 --port 8080
  --parallel 2 --metrics` (no `-ngl` — the edge demo is deliberately GPU-free to prove the
  CPU-only deployment shape).
- Envelope for a 4B Q4_K_M: ~2.5–3 GB weights + ~0.5–1.5 GB KV in RAM. **Benchmark on the
  actual host/llama.cpp pair and record it** — `just bench-edge`
  (`ops/runbooks/edge-bench.md`), which also samples package watts via Intel RAPL when
  readable; results labeled `platform: x86-local`.
- Telemetry: llama-server `/metrics` + the dev-mode demo publisher feed
  `sanad_edge_watts`, `sanad_edge_gpu_util`, `sanad_edge_temp_c` via the API SSE bridge.

## 6.3 ModelRouter contract

The API never hardcodes upstreams. `services/inference_router.py` maps
`model_alias → {upstream_kind: vllm|llamacpp, base_url, served_name}` from the registry table;
health-checks upstreams every 15 s; exposes availability in `/v1/models`.

**Contract note:** everything upstream of the gateway speaks the OpenAI Chat Completions dialect, so
ModelRouter only ever swaps base URLs — never add a second wire format.
