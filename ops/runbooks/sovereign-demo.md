# Runbook: air-gapped sovereign demo (one box, Wi-Fi off)

Goal: the P5/P6 acceptance demo — the full stack running with **zero egress**, provably.

## Prepare (online, before the demo)

1. `just check` green; images built and side-loaded:
   `docker save sanad-api sanad-web vllm-image | ssh demo-box docker load` (or pull from
   on-prem Harbor).
2. Models mirrored to the box: `mc mirror sanad/sanad-models /opt/sanad/models` — verify
   sha256 against `manifest.json`.
3. Tokenizer files pre-synced to `SANAD_TOKENIZERS_DIR` (fertility endpoint needs them —
   no hub fallback in sovereign mode).
4. `.env`: `SANAD_MODE=sovereign`.

## Run

```bash
# Wi-Fi OFF / ethernet unplugged, then:
docker compose -f infra/compose/docker-compose.yml \
               -f infra/compose/compose.sovereign.yml \
               --profile gpu up -d
```

## Verify sovereignty (the demo IS the verification)

- [ ] `curl localhost:8000/readyz` → ready with all checks true
- [ ] Chat streams Arabic with correct ligatures; `x_sanad.sovereign=true` on the final frame
- [ ] FertilityField hero regroups on tokenizer switch (live `/v1/tokenize/fertility`)
- [ ] `docker network inspect sanad_sanad-internal | grep '"Internal": true'`
- [ ] No egress attempts: `docker compose logs | grep -iE 'huggingface|fetch|download'` empty
- [ ] On k3s instead of compose: `SanadSovereignEgress` alert green for 24 h (§10 checklist)

## Rollback

`docker compose down` (volumes persist); flip `.env` back to `SANAD_MODE=dev` for online work.
