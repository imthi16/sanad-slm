# network module — VPC/subnets/SGs for cloud envs; a no-op shell on-prem (§9.1).
variable "env" { type = string }

variable "cidr" {
  type    = string
  default = "10.40.0.0/16"
}

resource "aws_vpc" "sanad" {
  cidr_block           = var.cidr
  enable_dns_hostnames = true
  tags                 = { Name = "sanad-${var.env}", Project = "sanad" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.sanad.id
  tags   = { Name = "sanad-${var.env}-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.sanad.id
  cidr_block              = cidrsubnet(var.cidr, 8, 1)
  map_public_ip_on_launch = true
  tags                    = { Name = "sanad-${var.env}-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.sanad.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "sanad-${var.env}-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

output "vpc_id" { value = aws_vpc.sanad.id }
output "public_subnet_id" { value = aws_subnet.public.id }
