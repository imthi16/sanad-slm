# CLAUDE.md — `apps/api/` · FastAPI gateway

> Loads when Claude works under `apps/api/`. The root [`CLAUDE.md`](../../CLAUDE.md) holds the prime
> directives and the mode matrix — read it first; it wins on conflict.

## 7.1 Principles

Async end-to-end; OpenAI-compatible passthrough for chat (so any OSS client works) **augmented**
with Sanad metadata (latency, token usage, detected lang, sovereign flag); strict CORS from
settings; security headers middleware (CSP self-only, X-Content-Type-Options, HSTS in prod);
problem+json error shape; Redis token-bucket rate limit (per-IP dev, per-key prod); every route
carries Prometheus histograms (`sanad_api_request_seconds{route,method,status}`).

## 7.2 Endpoints (v1)

| Method & path | Purpose |
|---|---|
| `POST /v1/chat/completions` | OpenAI-compatible; streams SSE when `stream=true`; routes by `model` alias; appends `x_sanad` usage block on final chunk |
| `GET /v1/models` | Aliases + upstream health + quant format + license from manifests |
| `GET /v1/eval/runs` · `GET /v1/eval/runs/{id}` | Benchmark scores, 3C3H per-dim, agreement stats (α, κ, heatmap), efficiency panel |
| `POST /v1/eval/runs/{id}/ingest` | CLI/K8s eval-job posts `reports/*.json` here (bearer service token) |
| `GET /v1/telemetry/stream` | SSE fan-out of edge/GPU metrics (Redis pub/sub bridge) |
| `POST /v1/tokenize/fertility` | `{text}` → per-tokenizer token counts/segments (powers the 3D hero) |
| `GET /v1/registry/artifacts` | Model versions, sha256, cosign status, lineage graph |
| `GET /healthz` · `GET /readyz` | Liveness (process) / readiness (DB+Redis+≥1 upstream) |

## 7.3 Canonical patterns

Read `src/sanad_api/main.py` (lifespan wiring: settings, pooled `httpx.AsyncClient`, async engine,
redis pool, model-router refresh task) and `src/sanad_api/routers/chat.py` (the SSE proxy) and copy
their shapes. The two invariants those files encode, which are not obvious from the code alone:

- **Chat streaming is a passthrough, not a re-serialisation.** Upstream OpenAI chunks are forwarded
  verbatim; Sanad's own numbers ride in one extra final frame (`x_sanad`: ttft, tok/s, lang). Do not
  parse-and-rebuild chunks — the chunk-integrity test exists because that regression is invisible in
  manual testing.
- **`EventSourceResponse(gen(), ping=15000)`** — the ping keeps air-gapped proxies from reaping the
  stream.

DB tables (SQLAlchemy 2.0, Alembic-managed): `eval_runs`, `benchmark_scores`, `judge_scores`
(judge, dim, score, item_id), `agreement_stats`, `artifacts`, `telemetry_snapshots`,
`chat_usage`. Chat **content is not persisted** by default (sovereign posture) — only usage
metadata; a `SANAD_PERSIST_CHATS=true` dev flag exists for debugging.

## 7.4 Backend testing

pytest-asyncio unit tests for services; respx-mocked upstream tests for the SSE proxy (assert
chunk passthrough + final x_sanad frame); schemathesis run against the live OpenAPI in CI;
Alembic migration up/down smoke; coverage gate ≥ 80% on `services/` + `routers/`.

Tool config lives in this workspace's `pyproject.toml`; the inner-loop commands are in root
[`CLAUDE.md`](../../CLAUDE.md) §12.1.

Regenerate the web client after any endpoint change: `just api-types` (output in
`apps/web/src/lib/api/` is generated — never hand-edit).
