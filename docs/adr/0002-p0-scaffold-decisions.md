# ADR-0002: P0 scaffold — implementation choices within the CLAUDE.md spec

Date: 2026-07-02 · Status: accepted

## Context

CLAUDE.md §2–§9 fixes the architecture; scaffolding still required a handful of in-spec
implementation choices worth recording.

## Decisions

1. **Rate limiting** — Redis token bucket as an atomic Lua script (one round trip), keyed
   per-IP in dev / per-`X-API-Key` otherwise; fails **open** when Redis is down (an infra
   outage must not take chat down with it; abuse control < availability for a demo platform).
2. **SSE final frame** — the x_sanad stats ride a dedicated `{"object": "sanad.final"}` data
   frame *before* `[DONE]`, so stock OpenAI clients ignore it and the web client doesn't need
   a custom event type.
3. **Grapheme-safe streaming** — implemented as a `GraphemeBuffer` that withholds the last
   grapheme while it can still grow (lam-alef, shadda chains); flushed at stream end. Chosen
   over per-chunk `Intl.Segmenter` re-segmentation of the whole message for O(delta) cost.
4. **FertilityField atlas** — Arabic shaped as *whole words* rasterized via canvas `fillText`
   (platform shaping engine keeps ligatures); Latin split to graphemes. Raster atlas now,
   MSDF later behind the same `GlyphAtlas` interface. Budget enforced at 1,200 instances.
5. **tegrastats exporter** — stdlib + prometheus_client single file (no pip tree on JetPack);
   doubles as the API telemetry forwarder (best-effort POST, Prometheus scrape is truth).
6. **Egress-zero alert on stock k3s** — flannel exposes no per-destination flow metrics, so
   the rule alerts on sustained namespace transmit-over-receive overflow with a tunable
   ceiling, and a second rule fires if the NetworkPolicies (the *enforcement* layer) vanish.
   A cilium/hubble flow-based expression can replace it without chart surgery.
7. **k3s kubeconfig** — retrieved manually and SOPS-encrypted rather than written to TF state
   (state files travel; kubeconfigs shouldn't).
8. **Judge harness language** — items tagged `mixed` are judged with the Arabic rubric (the
   dominant script in our code-switch data is Arabic).

## Consequences

All are swappable behind stable interfaces; none change CLAUDE.md §2–§9 contracts.
