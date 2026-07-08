# prod env — cloud burst training + on-prem k3s + registries + observability (§9.1).
terraform {
  required_version = ">= 1.8"

  backend "s3" {
    bucket                      = "sanad-tfstate"
    key                         = "prod/terraform.tfstate"
    region                      = "me-central-1"
    use_lockfile                = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true
    skip_region_validation      = true
    use_path_style              = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.16"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.35"
    }
  }
}

provider "aws" {
  region = "me-central-1"
}

provider "kubernetes" {
  config_path = var.kubeconfig_path # exported to SOPS by the k3s module
}

provider "helm" {
  kubernetes {
    config_path = var.kubeconfig_path
  }
}

module "network" {
  source = "../../modules/network"
  env    = "prod"
}

module "gpu_train" {
  source        = "../../modules/gpu_train"
  env           = "prod"
  region        = "me-central-1"
  instance_type = var.train_instance_type
  spot          = true
  auto_stop_min = 30
  subnet_id     = module.network.public_subnet_id
  vpc_id        = module.network.vpc_id
  ssh_key_name  = var.ssh_key_name
}

module "k3s" {
  source = "../../modules/k3s_cluster"
  nodes  = var.onprem_nodes
}

module "registry" {
  source     = "../../modules/registry_minio_harbor"
  depends_on = [module.k3s]
}

module "obs" {
  source          = "../../modules/observability"
  sanad_namespace = "sanad"
  depends_on      = [module.k3s]
}

variable "train_instance_type" {
  type    = string
  default = "g5.2xlarge" # verify regional availability before apply (§9.1)
}

variable "ssh_key_name" {
  type    = string
  default = "sanad-prod"
}

variable "kubeconfig_path" {
  type    = string
  default = "~/.kube/sanad-prod" # decrypted from secrets/prod.sops.yaml by `just helm-deploy`
}

variable "onprem_nodes" {
  description = "on-prem k3s nodes reachable over SSH"
  type = list(object({
    host    = string
    user    = string
    role    = string # server | agent
    gpu     = bool
  }))
  default = []
}
