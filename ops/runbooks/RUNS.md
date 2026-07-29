# Run orchestration — what produced the numbers in `RESULTS.md`

These are the chains that actually ran the pipeline, promoted out of the repo root where they were
written. They are kept for **prime directive 4** (reproducibility): `RESULTS.md` traces every figure
to a report hash, and these are what generated those reports. Each script's header carries the
reasoning for its stage ordering — read it before re-running.

Two properties they all share, and the reason they are gate-ordered rather than convenient:
each stage gates the next, because falling through a red gate into a multi-hour stage produces
artifacts nobody can quote; and they are ordered cheapest-and-most-certain first, so a late failure
still leaves the earlier evidence on disk.

| Script | Phase | What it does | Writes |
|---|---|---|---|
| `p23-train-quantize.sh` | P2→P3 | Train + merge, then AWQ, GGUF, gates, edge bench — the full unattended chain | train + quant reports |
| `p3-quantize.sh` | P3 | AWQ → ppl-gate → GGUF+imatrix → ppl-gate → bench-edge. **Deliberately does not retrain** — `out/merged-bf16` is the input | quant reports |
| `p3b-gguf-gate.sh` | P3 | Re-runs the GGUF gate with matched methodology (f16 GGUF baseline, `llama-perplexity` on both sides). Entirely CPU | GGUF gate report |
| `p4-benchmarks.sh` | P4 | Standardized benchmarks, fine-tuned vs base, cheapest-first | `evals/reports/` harness output |
| `p4b-comparators.sh` | P4 | Closes the quantization gate's ArabicMMLU clause and fills the comparator column | harness + comparator output |
| `p5-e2e.py` | P5 | Proves the app end to end on the CPU-only box against our own GGUF: `llama-server` ← `sanad-api` (ModelRouter) ← HTTP client. No Docker, no GPU — the ADR-0004 edge shape for real | **`ml/evals/reports/p5_e2e.json`** (tracked) |
| `demo-bilingual-chat.py` | P5 | Bilingual demo through `llama-server`'s OpenAI-compatible endpoint — the §6.2 serving path, not a convenience shortcut | transcript |
| `toolcall-diagnose.py` | open issue | Isolates the stray `<tool_call>` leak: chat template (applied) vs raw completion (no template) | stdout |
| `toolcall-control.sh` | open issue | The control the earlier investigations lacked: **does the base model do it too?** | stdout |

`edge-bench.sh` (documented in `edge-bench.md`) and the `train-4090.md` / `sovereign-demo.md`
runbooks predate these and are unchanged.

## Open issue these last two belong to

`RESULTS.md` records that the served model emits stray `<tool_call>` tokens and that **no claim
about the served model's output should be made until the cause is understood**. `toolcall-diagnose.py`
and `toolcall-control.sh` are the two halves of that investigation — keep them until it closes.

## Not promoted

The one-shot scripts that drove a **rented GPU box** (SSH launch, armed 18:30 timers, artifact
fetch-and-verify, post-run erase) were deleted rather than promoted: the box no longer exists, they
hardcoded its address, and their outputs are superseded by the hashed reports in
`ml/evals/reports/`. The same goes for the append-logs they wrote — every headline figure in them
(peak VRAM 15.59 GB, ArabicMMLU 59.33 / 59.79 / 57.58, ALLaM 70.01) is recorded in `RESULTS.md`.

SSH credentials in those scripts were read from `SANAD_SSH_PASS`, never hardcoded. The scripts kept
here reach only `127.0.0.1`.
