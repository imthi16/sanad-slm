# gpu_train — one spot GPU instance in me-central-1 for QLoRA bursts (§9.1).
# Includes the COST GUARD: CPU idle 30 min → auto-stop alarm.

variable "env" { type = string }
variable "region" { type = string }
variable "instance_type" {
  type    = string
  default = "g5.2xlarge" # verify regional availability before apply
}
variable "spot" {
  type    = bool
  default = true
}
variable "auto_stop_min" {
  type    = number
  default = 30
}
variable "subnet_id" { type = string }
variable "vpc_id" { type = string }
variable "ssh_key_name" { type = string }
variable "allowed_ssh_cidr" {
  type    = string
  default = "0.0.0.0/0" # tighten to the team VPN in prod tfvars
}

data "aws_ami" "dlami" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_security_group" "train" {
  name_prefix = "sanad-train-${var.env}-"
  vpc_id      = var.vpc_id

  ingress {
    description = "ssh"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }
  egress {
    description = "all egress (dev-mode training box; sovereign serving is on-prem)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Project = "sanad" }
}

resource "aws_instance" "train" {
  ami                    = data.aws_ami.dlami.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [aws_security_group.train.id]
  key_name               = var.ssh_key_name

  dynamic "instance_market_options" {
    for_each = var.spot ? [1] : []
    content {
      market_type = "spot"
      spot_options {
        instance_interruption_behavior = "stop"
        spot_instance_type             = "persistent"
      }
    }
  }

  root_block_device {
    volume_size = 200
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    repo_url = "https://github.com/OWNER/sanad.git" # set in tfvars
  })

  tags = { Name = "sanad-train-${var.env}", Project = "sanad", AutoStop = "true" }
}

# COST GUARD: stop when CPU idles 30 min — a forgotten box must stop itself (§9.1)
resource "aws_cloudwatch_metric_alarm" "idle_stop" {
  alarm_name          = "sanad-train-${var.env}-idle-stop"
  alarm_description   = "auto-stop the training box after ${var.auto_stop_min}m of idle CPU"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = ceil(var.auto_stop_min / 5)
  threshold           = 5
  comparison_operator = "LessThanThreshold"
  dimensions          = { InstanceId = aws_instance.train.id }
  alarm_actions       = ["arn:aws:automate:${var.region}:ec2:stop"]
}

output "public_ip" { value = aws_instance.train.public_ip }
output "instance_id" { value = aws_instance.train.id }
