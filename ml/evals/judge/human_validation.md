# Human validation protocol (§5.4c)

**No judge-based claim ships without the human↔judge κ from this protocol** (prime directive 5).

## Sample

- 50 items, stratified from the judged grounded-QA pool of the run:
  25 AR / 20 EN / 5 code-switch; within each language, half from the high-disagreement
  `human_queue.jsonl`, half sampled uniformly from the remainder (seed 3407).

## Rater

- One native Arabic speaker with banking-domain familiarity (record initials + date).
- The rater sees exactly what the judges saw: question, gold reference, grounding, and the
  model answer — **never** the judges' scores (blind).

## Procedure

1. Rater applies the same rubric (`rubric_ar.md` / `rubric_en.md`), producing the same strict
   JSON per item.
2. Save one line per item to `evals/reports/<run_id>/human_scores.jsonl`:
   `{"item_id": "...", "correct": true, "completeness": 4, ..., "rater": "XX", "date": "YYYY-MM-DD"}`
3. Re-run `just judge <run_id>` (agreement step) — it computes human↔judge Cohen's κ on the
   correctness gate and writes it into `judge_3c3h.json` + `agreement.json`.

## Reporting

- Quote κ with its sample size (n=50) wherever a 3C3H score is claimed.
- κ < 0.4 (poor agreement): judge scores for that run are demoted to "indicative only" and the
  eval report must say so; investigate rubric or judge quality before re-claiming.
