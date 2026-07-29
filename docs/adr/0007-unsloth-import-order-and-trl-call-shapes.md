# ADR-0007: Import Unsloth first; treat TRL's call shapes as contract

Date: 2026-07-28 · Status: accepted · Relates to: ADR-0006 (the pin set this sits on)

## Context

Three P2 runs died before a single training step, each at a later point than the last:

| Run | Died at | Cause |
|---|---|---|
| 2026-07-26 18:49 | `import unsloth` | `trl>=1.0` floor resolved an Unsloth that cannot import — ADR-0006 |
| 2026-07-27 18:42 | `get_peft_model` | `target_modules: all-linear` iterated into characters — `2caedb2` |
| 2026-07-28 08:58 | `SFTTrainer(...)` | `eos_token ('<EOS_TOKEN>') is not found in the vocabulary` |

The third is the subject here, along with a fourth found while reproducing it.

**Unsloth patches by rebinding, and rebinding does not reach names already bound.** On import,
Unsloth replaces `trl.SFTTrainer` and `trl.SFTConfig` with its own subclasses. `sft.py` imported
`from trl import SFTConfig, SFTTrainer` *before* `from unsloth import FastLanguageModel`, so those
names kept pointing at stock TRL:

```
MARK trl-first SFTTrainer : trl.trainer.sft_trainer     <- what sft.py bound
MARK trl.SFTTrainer now   : UnslothSFTTrainer           <- what Unsloth installed
MARK bound is patched?    : False
```

The run therefore drove an Unsloth-patched model and tokenizer through the stock TRL trainer. In
that mismatched state `args.eos_token` arrives as the sentinel `<EOS_TOKEN>`: Unsloth's trainer
knows to resolve it against the tokenizer, stock TRL validates it literally, finds no such token
in Qwen3's vocabulary (its real EOS is `<|im_end|>`), and raises.

Unsloth prints a `UserWarning` about exactly this on every run. It was visible in the very first
failure on 2026-07-26 and read as cosmetic. It was not.

**`formatting_func`'s input shape varies while its output shape does not.** Correcting the import
order moved the failure into `_prepare_dataset`, whose contract is asymmetric:

* it first probes with a **single example**, `formatting_func(next(iter(dataset)))`, where
  `messages` is one conversation — yet still requires a `list` back, because it immediately takes
  `test_text[0]` to sniff for a duplicate BOS;
* it then maps with `batched=True`, where `messages` is a list of conversations and the return
  must hold one string per conversation.

Both halves were got wrong in turn. Assuming the batched shape made the probe iterate one
conversation's individual messages and hand a bare `{role, content}` dict to the chat template —
`jinja2.UndefinedError: dict object has no element 0`. Returning a bare string for the probe
instead raised `Unsloth: The formatting_func should return a list of processed strings`. Neither
message names the function or the shape at fault.

## Decisions

1. **`import unsloth` precedes trl/transformers/peft in `sft.py`**, with a comment saying why, and
   `# isort: skip` so a formatter cannot quietly reorder it into breakage. The import is for side
   effects; `# noqa: F401` documents that.
2. **`formatting_func` accepts both input shapes and always returns `list[str]`**, disambiguating
   on the first element rather than on a `batched` flag that is not passed: a conversation's
   elements are dicts, a batch's are lists. The uniform return is the invariant worth remembering —
   a single example yields a one-element list, not a string.
3. **Both are pinned by static, dependency-free tests** (`tests/test_formatting_and_import_order.py`).
   The import order is asserted by walking `sft.py`'s AST — no torch, no CUDA, no weights — so CI
   catches a reordering that would otherwise only appear minutes into a GPU run. The call shapes
   are covered against a fake tokenizer that rejects anything which is not a conversation.

## Consequences

Every failure in the table above shares a shape: a library-contract mismatch invisible to ruff,
mypy and the unit suite, reachable only with a warm GPU, and costing hours per iteration. The
response is not more care at the keyboard but more of the contract asserted cheaply:

- ADR-0006 added preflight's real-import probe (catches failure 1).
- `2caedb2` added `resolve_target_modules` plus torch-free tests (catches failure 2).
- This ADR adds the AST import-order guard and the call-shape tests (catches 3 and 4).

That is three separate guards bolted on after the fact, which is the honest summary: `train/sft.py`
had never executed end-to-end, so each of its integration points was unverified. The remaining
unexercised stretch is everything past trainer construction — the TRL loop itself, `merge.py`, AWQ,
and the CPU imatrix path. Expect the same class of problem there, and prefer extending these
cheap static guards over discovering the next one at runtime.

A note against future confusion: the sentinel's exact origin inside Unsloth was not isolated. What
was established empirically is narrower and sufficient — with the corrected import order the
`eos_token` check passes and execution proceeds to `_prepare_dataset`. If it resurfaces, start from
whether `trl.SFTTrainer is` the Unsloth subclass at the call site.
