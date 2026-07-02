# secrets/

Real secrets live here **only** as SOPS-encrypted files (`*.sops.yaml`), encrypted to the age
recipients listed in the repo-root `.sops.yaml`. Nothing plaintext is ever committed — the
pre-commit `gitleaks` + `detect-private-key` hooks and `.gitignore` enforce this.

```bash
# encrypt
sops --encrypt --in-place secrets/prod.sops.yaml
# decrypt for helm deploys (done by `just helm-deploy`)
sops --decrypt secrets/prod.sops.yaml
```

Expected files (create per environment, never commit plaintext):

- `dev.sops.yaml` — compose-stack overrides (API service token, MinIO root creds)
- `prod.sops.yaml` — k3s kubeconfig, Harbor robot token, API service tokens, Grafana admin
- `edge.sops.yaml` — Ansible vault-equivalent per-device secrets
