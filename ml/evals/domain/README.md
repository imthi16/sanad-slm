# sanad_bank_eval_v1 — domain evaluation set

**Target: 300 own-authored held-out items** (150 AR / 120 EN / 30 code-switch), CC-BY-4.0,
covering extraction (exact-match/F1), classification (accuracy/macro-F1) and grounded QA
(3C3H-judged). See CLAUDE.md §5.4b.

Status: `sanad_bank_eval_v1.jsonl` currently holds **seed items** written to establish the
format and difficulty bar. Before P4 sign-off:

1. Grow to the full 300-item distribution (authored + reviewed by a native speaker; reviewer
   initials in `source.reviewer`).
2. Freeze: commit the file, record its sha256 in `configs/eval/domain_bank.yaml`
   (`expected_sha256`) and in the P4 eval report.
3. **Contamination hygiene (BALSAM-style):** these items never enter any training set; the
   dedup pass treats this file as a blocklist. Treat the set as private — do not paste items
   into public issues/README.

Item shape = the standard record schema plus an `eval` block:

```json
{"eval": {"task": "extraction | classification | grounded_qa",
           "answer": "<gold>", "choices": ["..."], "grounding": "<source snippet>"}}
```
