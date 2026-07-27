# ADR-0006: Unsloth pins the training stack; TRL ≥ 1.0 is off the table

Date: 2026-07-27 · Status: accepted · Amends: CLAUDE.md §3.1 (fine-tuning and GPU-quant rows)

## Context

The first P2 attempt aborted nine seconds into `just train` on 2026-07-26:

```
ImportError: cannot import name 'ConstantLengthDataset' from 'trl.trainer.utils'
```

`ml/pyproject.toml` required `trl>=1.0`, per CLAUDE.md §3.1 ("TRL v1 unified `SFTTrainer`"). But
**Unsloth caps TRL below 1.0 in every release it has ever published**, current one included:
`trl!=0.19.0,<=0.24.0,>=0.18.2`. Those two constraints have no solution together.

uv did not report that as a conflict, because `unsloth>=2025.3` had no upper bound. It satisfied
both by walking Unsloth backwards to 2025.7.2 — a year old, and the last build whose metadata
left TRL unbounded — and pairing it with trl 1.7.0. Every module was present and importable in
isolation; the graph as a whole could not import, because TRL 1.0 moved `ConstantLengthDataset`
out of `trl.trainer.utils` and unsloth-zoo 2025.7.4 still reaches for it there.

This is the failure mode a version floor with no ceiling produces: not a resolution error, but a
silent downgrade of the component that was supposed to be current.

Two further conflicts surfaced once `unsloth>=2026.7` was floored:

1. **A macOS requirement leaked into a Linux-only solve.** unsloth-zoo depends on `mlx-vlm` under
   `sys_platform == 'darwin' and platform_machine == 'arm64'`, and mlx-vlm demands
   `transformers>=5.14`. uv resolves universally by default, so that darwin-only floor propagated
   into the shared solve and made every `llmcompressor` below 0.12 unsatisfiable — on a project
   that never runs on macOS.
2. **`train` and `quant` share one venv.** The P2/P3 orchestration does
   `uv sync --extra train --extra quant` once, so llm-compressor must fit inside Unsloth's
   windows. 0.12 needs `transformers>=5.9` (Unsloth caps 5.5); 0.11 needs `datasets>=4.8.4`
   (Unsloth caps `<4.4`). Only 0.10.x overlaps on both axes.

## Decisions

1. **Drop the TRL ≥ 1.0 requirement.** The `train` extra now tracks Unsloth's supported window:
   `trl>=0.18.2,!=0.19.0,<=0.24`. TRL's major version is not load-bearing for any claim in the
   paper; the <16 GB peak-VRAM property that the $0-on-one-4090 story rests on *is*, and that is
   Unsloth's contribution. Where the two conflict, Unsloth wins.
2. **Floor Unsloth at `>=2026.7`.** This is the constraint that prevents the silent backtrack from
   recurring. Every other ceiling in the extra (`torch<2.12`, `transformers<=5.5`, `datasets<4.4`,
   `peft>=0.18`, `bitsandbytes!=0.48.0`) mirrors Unsloth's own metadata, so an incompatible
   combination now fails at lock time instead of at import time.
3. **Restrict the ml workspace to `linux-x86_64`** via `[tool.uv] environments`. The train box,
   the CPU edge box and the dev workstation are all x86_64 Linux (ADR-0004). Nothing is lost, and
   the darwin-only mlx-vlm branch stops constraining a solve it will never participate in.
4. **Pin `llmcompressor>=0.10,<0.11`.** The newest release that coexists with Unsloth. Raising it
   requires re-checking `datasets` *and* `transformers` together — the two axes moved
   independently across 0.10 → 0.11 → 0.12.
5. **Preflight imports the training stack for real** (`check_train_imports`). `find_spec` proves a
   directory exists; it never runs an `__init__`. Preflight reported 14 passed / 0 blocking one
   second before the import died, which made it worse than useless — it authorised the run. It now
   executes `import unsloth, trl, peft` in a bounded subprocess and fails on the exception text.

## Consequences

Resolved set: torch 2.10.0 · transformers 4.57.6 · trl 0.24.0 · peft 0.19.1 · datasets 4.3.0 ·
unsloth 2026.7.5 · unsloth-zoo 2026.7.6 · bitsandbytes 0.49.2 · llmcompressor 0.10.0.2.

`train/sft.py` is unchanged — TRL 0.24's `SFTTrainer` takes the same arguments the script already
passes, and Unsloth is the layer that actually constructs the model.

The cost is that this stack is pinned to a ceiling set by a third party's compatibility matrix.
When Unsloth widens its TRL/transformers windows, four pins move together or none do. The upside
is that the constraint is now written down in one place and enforced twice — at lock time by the
explicit ceilings, and at run time by preflight's import probe.

An alternative was considered and rejected: keep TRL ≥ 1.0 and drop Unsloth for plain TRL
`SFTTrainer` + PEFT DoRA + bitsandbytes NF4. It honours §3.1 as written and removes the third-party
ceiling entirely, but it puts the <16 GB peak-VRAM acceptance criterion (§13 P2) back into
question and rewrites the load path in a file that has never once executed successfully. Not a
change to make on the night the pipeline is meant to run; revisit if Unsloth stops tracking
upstream.
