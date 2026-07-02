# k3s_cluster — on-prem nodes over SSH: k3s server+agents, GPU node labeled
# sanad.ai/gpu=true, NVIDIA device plugin (§9.1). Plain k3s, no operator authoring (non-goal).

variable "nodes" {
  type = list(object({
    host = string
    user = string
    role = string # server | agent
    gpu  = bool
  }))
}

variable "k3s_version" {
  type    = string
  default = "v1.32.3+k3s1"
}

locals {
  servers = [for n in var.nodes : n if n.role == "server"]
  agents  = [for n in var.nodes : n if n.role == "agent"]
  server  = length(local.servers) > 0 ? local.servers[0] : null
}

resource "terraform_data" "k3s_server" {
  count = local.server != null ? 1 : 0

  connection {
    type = "ssh"
    host = local.server.host
    user = local.server.user
  }

  provisioner "remote-exec" {
    inline = [
      "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION='${var.k3s_version}' sh -s - server --disable traefik --write-kubeconfig-mode 640",
      "sudo cat /var/lib/rancher/k3s/server/node-token > /tmp/node-token",
    ]
  }
}

resource "terraform_data" "k3s_agents" {
  for_each   = { for i, n in local.agents : "${n.host}" => n }
  depends_on = [terraform_data.k3s_server]

  connection {
    type = "ssh"
    host = each.value.host
    user = each.value.user
  }

  provisioner "remote-exec" {
    inline = [
      "TOKEN=$(ssh ${local.server.user}@${local.server.host} cat /tmp/node-token)",
      "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION='${var.k3s_version}' K3S_URL='https://${local.server.host}:6443' K3S_TOKEN=\"$TOKEN\" sh -",
      # GPU nodes get the scheduling label the vllm chart selects on
      each.value.gpu ? "sudo k3s kubectl label node $(hostname) sanad.ai/gpu=true --overwrite" : "true",
    ]
  }
}

# NVIDIA device plugin on the labeled GPU nodes
resource "terraform_data" "device_plugin" {
  count      = local.server != null ? 1 : 0
  depends_on = [terraform_data.k3s_agents]

  connection {
    type = "ssh"
    host = local.server.host
    user = local.server.user
  }

  provisioner "remote-exec" {
    inline = [
      "sudo k3s kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.0/deployments/static/nvidia-device-plugin.yml",
    ]
  }
}

output "server_host" {
  value = local.server != null ? local.server.host : null
}
# kubeconfig retrieval → secrets/prod.sops.yaml is a documented manual step:
#   ssh <server> sudo cat /etc/rancher/k3s/k3s.yaml | sops encrypt → never plaintext in state
