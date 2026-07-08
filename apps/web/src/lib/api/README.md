# src/lib/api/ — GENERATED, never hand-edited

This directory is populated by `just api-types`:

```
FastAPI OpenAPI export → @hey-api/openapi-ts → typed client here
```

Working agreement #5: generated things are never hand-edited. Until the first generation runs,
pages use the thin untyped helpers in `src/lib/http.ts`; replace those call-sites with the
generated client as soon as `just api-types` has run.
