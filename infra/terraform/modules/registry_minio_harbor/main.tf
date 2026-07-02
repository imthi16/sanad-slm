# registry_minio_harbor — MinIO (models/tfstate) + Harbor (images) via helm_release (§9.1).
# Harbor project `sanad`: vuln-scan-on-push + cosign policy; sovereign admission verifies sigs.

variable "namespace" {
  type    = string
  default = "registry"
}

variable "minio_storage" {
  type    = string
  default = "500Gi"
}

resource "helm_release" "minio" {
  name             = "minio"
  namespace        = var.namespace
  create_namespace = true
  repository       = "https://charts.min.io/"
  chart            = "minio"
  version          = "5.4.0"

  values = [yamlencode({
    mode = "standalone"
    persistence = {
      size = var.minio_storage
    }
    buckets = [
      { name = "sanad-models", policy = "none", purge = false },
      { name = "sanad-tfstate", policy = "none", purge = false },
      { name = "mlflow", policy = "none", purge = false },
    ]
    # root creds come from a SOPS-decrypted existingSecret — never inline
    existingSecret = "minio-root"
    resources = {
      requests = { memory = "1Gi", cpu = "500m" }
    }
  })]
}

resource "helm_release" "harbor" {
  name             = "harbor"
  namespace        = var.namespace
  create_namespace = true
  repository       = "https://helm.goharbor.io"
  chart            = "harbor"
  version          = "1.16.0" # Harbor ≥ 2.12 app version (§3.5)

  values = [yamlencode({
    expose = {
      type = "clusterIP"
      tls  = { enabled = false } # terminated by the cluster ingress
    }
    externalURL = "https://harbor.sanad.local"
    # value is the name of a SOPS-provisioned K8s Secret, not a credential
    existingSecretAdminPassword = "harbor-admin" # gitleaks:allow
    trivy = { enabled = true } # scan on push
    persistence = {
      persistentVolumeClaim = {
        registry = { size = "200Gi" }
      }
    }
  })]
}
