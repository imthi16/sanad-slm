# Runbook — P1 data + P2 training on the RTX 4090 box

Target: a merged bf16 checkpoint with a lineage manifest, produced on the owner's workstation
(i9-14900K + RTX 4090 24 GB) at $0 (ADR-0003, ADR-0004).

**Read this first:** the only step that needs a human decision is the banking-pair curation in
stage 2. Everything else is a command whose failure mode is documented below it.

---

## 0. One-time setup (~15 min, needs network)

```bash
git clone https://github.com/imthi16/sanad-slm.git && cd sanad-slm
just setup                       # base + dev only: lint/type/test tooling
cd ml && uv sync --extra train   # the CUDA stack: torch, unsloth, trl, peft, bitsandbytes
```

`uv sync --extra train` pulls a few GB of CUDA wheels. It is the slow part of setup — start it
before reading the rest.

Check the driver can be seen:

```bash
nvidia-smi                       # confirm the 4090 and the driver version
just preflight                   # the authoritative check — see stage 3
```

<details>
<summary><b>If torch cannot see the GPU</b></summary>

`preflight` prints the torch build's CUDA version. A driver older than that build will not work.
Either update the NVIDIA driver or pin a torch built for the installed CUDA. Do not proceed with a
CPU fallback: a QLoRA run on CPU will not finish.
</details>

---

## 1. Data — ingest (~5 min, needs network)

```bash
just data
```

That runs, in order: `ingest_cidar` → `normalize` (NFC) → `langid` → `dedup` (MinHash) →
`split` → `manifest build`.

Then verify the gate and the split:

```bash
just data-gate                                     # licences must be Apache-2.0/CC-BY-4.0/MIT
wc -l ml/data/processed/splits/*.jsonl             # train + val record counts
grep -A6 'totals:' ml/data/MANIFEST.yaml           # counts, lang split, provenance split
```

**Expected:** ~10k CIDAR records, `provenance: native` at 100%, `lang_split` heavily `ar`, and a
val shard around 5% of the total. The split is seeded (3407) and stratified by
`(lang, provenance)`, so re-running `just data` reproduces it byte-for-byte.

<details>
<summary><b>Failure: <code>no records in data/processed</code></b></summary>

Ingest did not write anything. Check network, then run the ingest step alone to see the error:
`cd ml && uv run python data/scripts/ingest_cidar.py --limit 100`
</details>

<details>
<summary><b>Failure: <code>only N val records … a held-out loss curve on that is noise</code></b></summary>

The corpus is too small for a 5% holdout to mean anything. With CIDAR ingested this will not
happen. If you are deliberately testing on a small subset, pass `--min-val 0` to `split.py` and
treat the resulting val loss as decorative.
</details>

---

## 2. Data — your banking pairs (the only human step)

CIDAR alone trains a general Arabic instruction follower, not a banking model. The domain pairs
are what the whole claim rests on.

Author drafts as YAML under `ml/data/raw/bank/`, one file may hold many pairs:

```yaml
- question: "ما هي متطلبات اعرف عميلك للحسابات الجديدة؟"
  answer: "..."
  citation: "CBUAE Rulebook, AML/CFT Decision No. (20) of 2018, Art. 8"
  domain: banking.compliance
  lang: ar          # optional — re-checked by the langid pass
  reviewer: "MO"    # initials, required
```

Then validate and emit schema-valid records:

```bash
cd ml && uv run python data/scripts/curate_bank.py          # validate drafts only
cd ml && uv run python data/scripts/curate_bank.py --emit   # write records
```

Target from §5.1: **800–1,500 pairs, 60% AR / 30% EN / 10% code-switch**. `citation` and
`reviewer` are required by the template, and a PII scan runs over every draft — these are
enforced, not conventions.

Re-run `just data` afterwards so the new records are normalised, deduped and re-split.

> Separate from this: `ml/evals/domain/sanad_bank_eval_v1.jsonl` currently holds **12 of 300**
> held-out eval items. Those are the P4 credibility core and must never enter training. They are
> not needed for Monday's run.

---

## 3. Preflight (~10 s)

```bash
just preflight
```

Checks, each with a fix in its message: pinned base revision is a 40-char sha · GPU present,
≥ 20 GB, bf16-capable · `train` extra installed · both split shards exist and are non-empty ·
offline posture consistent with `SANAD_MODE` · HF credentials · free disk.

**Do not skip this.** Every check exists because its failure otherwise appears after the weights
have downloaded and the first epoch has started.

---

## 4. Train (hours)

```bash
just mlflow-ui   # http://localhost:5000 — leave running in another terminal
just train       # configs/train/qwen3-4b-qlora-dora.yaml
```

Canonical config, unchanged: Qwen3-4B-Instruct-2507 @ `cdbee75f…`, seed 3407, NF4 4-bit, LoRA
r16/α16 with DoRA on all-linear, 3 epochs, lr 2e-4 cosine, effective batch 16, packing on,
bf16, adamw_8bit, NEFTune α=5, max_seq_len 4096.

**Watch for:**

| Signal | Where | Acceptance (§13 P2) |
|---|---|---|
| Peak VRAM | MLflow `peak_vram_gb`, or `nvidia-smi` | **< 16 GB** |
| Val loss | MLflow, per epoch | monotone-ish; a rising curve means stop and re-check data |
| Cost | MLflow `cost_usd` | **$0** — local compute |

`sft.py` logs an error row if VRAM or cost exceeds budget, but does **not** abort: a run that
overshoots is still worth inspecting. Read the log rather than assuming success.

Outputs: `ml/out/adapter/` (LoRA weights) and `ml/out/merged-bf16/` (merged, with
`manifest.json` recording base → data hash → config hash).

<details>
<summary><b>OOM partway through</b></summary>

In order of preference: drop `per_device_batch` 4 → 2 and raise `grad_accum` 4 → 8 (same effective
batch); or lower `max_seq_len` to 2048. **Copy the config to a new file first** — §5.2 forbids
mutating the canonical one, because a changed config with the same name makes two runs
indistinguishable. `just train cfg=configs/train/<your-variant>.yaml`.
</details>

<details>
<summary><b>Run dies after the first epoch with no clear error</b></summary>

Usually the machine ran out of RAM (not VRAM) during checkpointing, or disk filled. `just
preflight` warns below 60 GB free; checkpoints accumulate under `ml/out/checkpoints/`.
</details>

---

## 5. After the run

```bash
just merge                       # adapter → merged bf16 + lineage manifest (if not already done)
ls -la ml/out/merged-bf16/
cat ml/out/merged-bf16/manifest.json
```

Archive the val-loss curve from MLflow — §13 P2 acceptance asks for it explicitly, and it is the
evidence that the run was healthy rather than merely finished.

**Next phase:** P3 quantize + serve — `just quant-awq`, `just quant-gguf`, then `just ppl-gate`,
which fails the release if quantization costs more than 3% (AWQ) / 5% (GGUF) perplexity per
language. The llama.cpp pin for that is already in `configs/quant/gguf-q4km.yaml`.

---

## Known prerequisites not solvable on the box

- **`meta-llama/Llama-3.2-3B-Instruct` is manually gated.** Meta approves each request by hand.
  Its tokenizer is one of the five in the fertility comparison, so `just fertility` cannot produce
  a complete table until access lands. Request it now if you have not — the wait is the blocker,
  not the code.
- **`inceptionai/jais-family-6p7b-chat` is auto-gated.** Accept the terms once while signed in and
  export `HF_TOKEN`.
- **`.sops.yaml` has a placeholder age recipient.** Needed before the first encrypted secret, not
  before training: `age-keygen -o ~/.config/sops/age/keys.txt`, then paste the public key in.
