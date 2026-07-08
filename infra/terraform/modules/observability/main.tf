# observability — kube-prometheus-stack + dcgm-exporter (GPU) + Loki, dashboards from
# ops/dashboards, and the signature egress-zero PrometheusRule (§9.1, §9.3).

variable "namespace" {
  type    = string
  default = "monitoring"
}

variable "sanad_namespace" {
  type    = string
  default = "sanad"
}

resource "helm_release" "kube_prometheus_stack" {
  name             = "kps"
  namespace        = var.namespace
  create_namespace = true
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = "70.4.0"

  values = [yamlencode({
    grafana = {
      admin = { existingSecret = "grafana-admin" }
      sidecar = {
        dashboards = { enabled = true, label = "grafana_dashboard" }
      }
    }
    prometheus = {
      prometheusSpec = {
        retention = "30d"
        ruleSelectorNilUsesHelmValues           = false
        serviceMonitorSelectorNilUsesHelmValues = false
        podMonitorSelectorNilUsesHelmValues     = false
      }
    }
  })]
}

resource "helm_release" "loki" {
  name       = "loki"
  namespace  = var.namespace
  repository = "https://grafana.github.io/helm-charts"
  chart      = "loki-stack"
  version    = "2.10.2"

  values = [yamlencode({
    loki     = { persistence = { enabled = true, size = "50Gi" } }
    promtail = { enabled = true }
  })]
  depends_on = [helm_release.kube_prometheus_stack]
}

resource "helm_release" "dcgm_exporter" {
  name       = "dcgm-exporter"
  namespace  = var.namespace
  repository = "https://nvidia.github.io/dcgm-exporter/helm-charts"
  chart      = "dcgm-exporter"
  version    = "4.0.4"

  values = [yamlencode({
    nodeSelector   = { "sanad.ai/gpu" = "true" }
    serviceMonitor = { enabled = true }
  })]
  depends_on = [helm_release.kube_prometheus_stack]
}

# dashboards from ops/dashboards land as ConfigMaps the grafana sidecar picks up
resource "kubernetes_config_map" "dashboards" {
  metadata {
    name      = "sanad-dashboards"
    namespace = var.namespace
    labels    = { grafana_dashboard = "1" }
  }
  data = {
    for f in fileset("${path.module}/../../../../ops/dashboards", "*.json") :
    f => file("${path.module}/../../../../ops/dashboards/${f}")
  }
  depends_on = [helm_release.kube_prometheus_stack]
}

# the egress-zero alert also ships inside the sovereign-guard chart; installing it here too
# keeps the alert alive even if the app charts are torn down (§9.3: firing = broken promise)
resource "kubernetes_manifest" "egress_zero_rule" {
  manifest = yamldecode(templatefile(
    "${path.module}/../../../../ops/alerts/egress-zero.yaml.tftpl",
    { namespace = var.sanad_namespace, monitoring_namespace = var.namespace }
  ))
  depends_on = [helm_release.kube_prometheus_stack]
}
