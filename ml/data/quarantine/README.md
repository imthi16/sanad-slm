# data/quarantine/ — research-only datasets

Datasets with **non-commercial or restrictive licenses** (AraFinNews, Fanar-derived,
jais-adapted, …) live here and **never** enter a `profile: commercial` train manifest.
The CI license gate (`data/scripts/manifest.py gate`) fails the build if any file under this
directory is referenced by `MANIFEST.yaml` `sources:`.

Rules (CLAUDE.md prime directive 2):

- Contents are gitignored; only this README is tracked.
- Experiments using quarantined data are tagged `research-quarantine` in MLflow and their
  adapters/checkpoints are never pushed to the MinIO release registry.
- Anything trained on quarantined data cannot pass `registry/push.py` (it checks lineage).
