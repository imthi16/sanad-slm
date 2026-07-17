# dev env — thin composition of modules; no resources at root (§9.1).
terraform {
  required_version = ">= 1.8" # OpenTofu ≥ 1.8 / Terraform ≥ 1.10

  backend "s3" {
    # MinIO S3-compatible backend with native lockfile — no DynamoDB (§3.5)
    bucket                      = "sanad-tfstate"
    key                         = "dev/terraform.tfstate"
    region                      = "me-central-1"
    use_lockfile                = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true
    skip_region_validation      = true
    use_path_style              = true
    # endpoint via env: AWS_ENDPOINT_URL_S3=http://minio:9000
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 3.0"
    }
  }
}

provider "aws" {
  region = "me-central-1" # data residency: training data never leaves the UAE region
}

module "network" {
  source = "../../modules/network"
  env    = "dev"
}

module "gpu_train" {
  source        = "../../modules/gpu_train"
  env           = "dev"
  region        = "me-central-1"
  instance_type = var.train_instance_type
  spot          = true
  auto_stop_min = 30
  subnet_id     = module.network.public_subnet_id
  vpc_id        = module.network.vpc_id
  ssh_key_name  = var.ssh_key_name
}

variable "train_instance_type" {
  description = "GPU instance for QLoRA bursts — verify me-central-1 availability before apply"
  type        = string
  default     = "g5.2xlarge"
}

variable "ssh_key_name" {
  type    = string
  default = "sanad-dev"
}

output "gpu_train_public_ip" {
  value = module.gpu_train.public_ip
}
