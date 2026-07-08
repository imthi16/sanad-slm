# ADR-0001: Record architecture decisions

Date: 2026-07-02 · Status: accepted

## Context

CLAUDE.md is the single source of truth for the current architecture, but the *history* of
why decisions changed needs its own trail — CLAUDE.md gets edited in place, ADRs don't.

## Decision

Every architectural change lands as a PR that updates CLAUDE.md **and** adds a numbered ADR
here (working agreement #2). Format: Context / Decision / Consequences, one page max.

## Consequences

Reviewers can audit the decision trail without diffing CLAUDE.md across history; the paper's
"design rationale" section cites ADRs directly.
