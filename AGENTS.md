# Repository Guidelines

## Project Structure & Module Organization

Sanad is a monorepo for a sovereign bilingual SLM platform. Read `CLAUDE.md` before major
changes; it is the source of truth when docs disagree.

- `ml/`: separate Python 3.12 `uv` workspace for data curation, training, quantization,
  evaluation, registry tooling, and ML tests in `ml/tests/`.
- `apps/api/`: separate Python 3.12 `uv` workspace for the FastAPI gateway, Alembic
  migrations, routers/services/schemas under `src/sanad_api/`, and tests in `tests/`.
- `apps/web/`: React 19 + Vite + TypeScript app. UI code is under `src/`, unit tests under
  `tests/`, and Playwright specs under `e2e/`.
- `infra/`, `serving/`, and `ops/`: OpenTofu/Helm, vLLM/llama.cpp serving, dashboards,
  alerts, and runbooks.
- `docs/adr/`: architecture decision records. Add one for architecture-level changes.

## Build, Test, and Development Commands

Use `just --list` as the command index.

- `just setup`: sync both Python workspaces, install web dependencies, and install pre-commit.
- `just dev`: start the local compose services plus API reload server and Vite web app.
- `just check`: full local PR gate: lint, format checks, type checks, tests, data gate, and
  CDN scan.
- `just api-types`: regenerate the generated TypeScript API client from FastAPI OpenAPI.
- `just data-gate` / `just verify-no-cdn`: run the license/provenance and sovereign web gates.

## Coding Style & Naming Conventions

Python uses Ruff formatting/linting, 100-character lines, Python 3.12, and strict mypy. Keep
the `ml/` and `apps/api/` dependency trees separate. TypeScript uses Biome with 2-space
indentation, double quotes, semicolons, and 100-character lines. Prefer descriptive module names;
tests follow `test_*.py` for pytest and `*.test.ts` / `*.spec.ts` for web tests.

## Testing Guidelines

Run focused tests in the affected workspace, then `just check` before declaring work done.
API CI enforces pytest coverage for routers/services at 80%. UI changes should include Vitest
coverage where practical and Playwright LTR plus RTL evidence for layout-sensitive work.

## Commit & Pull Request Guidelines

Use conventional commits, e.g. `feat(api): add telemetry endpoint` or `fix(web): preserve RTL
streaming`. Keep PRs small and phase-scoped. PRs should explain behavior changes, list commands
run, link issues when relevant, include screenshots for UI changes, justify new dependencies, and
update `CLAUDE.md` plus an ADR for architecture changes.

## Security & Configuration Tips

Never commit secrets, model weights, raw datasets, or hand-edited generated artifacts. Generated
clients, fertility reports, and eval outputs must be produced by the documented commands. Preserve
sovereign-mode constraints: no CDN assets, external fonts, unpinned model fetches, or bypasses of
license gates.
