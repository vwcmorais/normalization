terraform {
  required_version = "~> 0.15"
  backend "s3" {
    encrypt              = true
    bucket               = "catholabs-terraform-state"
    workspace_key_prefix = "role-normalization"
    key                  = "ab_redis"
    region               = "us-east-1"
  }
}

provider "aws" {
  region = var.region
}

locals {
  service_name = "catho-role-normalization-ab_redis"
  service_name_short = "catho-role-norm-ab_redis"
  service_desc_name = "Catho Role Normalization AB API REDIS"
  short_name = "ab.redis.rolenorm"

  // High Availability
  enable_ha = false
}

// Data for the SG                  
data "terraform_remote_state" "api" {
  backend = "s3"
  config = {
    encrypt              = true
    bucket               = "catholabs-terraform-state"
    workspace_key_prefix = "role-normalization"
    key                  = "api"
    region               = "us-east-1"
  }
  workspace = terraform.workspace
}


// Security Group
resource "aws_security_group" "redis_security_group" {
  name        = "${local.service_name}-${terraform.workspace}"
  description = "${local.service_desc_name} security group - ${terraform.workspace}"
  vpc_id      = var.vpc_id
  tags = merge(var.default_tags, { "Name" = "${local.service_name}-${terraform.workspace}" })
}

// Security Group Rules
resource "aws_security_group_rule" "egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.redis_security_group.id
}
resource "aws_security_group_rule" "ingress_self" {
  type              = "ingress"
  from_port         = 6379
  to_port           = 6379
  protocol          = "tcp"
  self              = true
  security_group_id = aws_security_group.redis_security_group.id
}
// Allow API SG
//resource "aws_security_group_rule" "ingress_api" {
  //type              = "ingress"
  //from_port         = 6379
  //to_port           = 6379
  //protocol          = "tcp"
  //source_security_group_id = data.terraform_remote_state.api.outputs.ec2_security_group
  //security_group_id = aws_security_group.redis_security_group.id
//}

// Subnet Group
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${replace(local.service_name_short,"_","-")}-${terraform.workspace}"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = "${replace(local.service_name_short,"_", "-")}-${terraform.workspace}"
  replication_group_description = "${local.service_desc_name} cluster - ${terraform.workspace}"

  automatic_failover_enabled    = local.enable_ha
  availability_zones            = local.enable_ha ? ["${var.region}a", "${var.region}c"] : ["${var.region}c"]
  multi_az_enabled              = local.enable_ha
  subnet_group_name             = aws_elasticache_subnet_group.redis.name
  port                          = 6379

  node_type                     = terraform.workspace == "prod" ? "cache.t3.medium" : "cache.t2.micro"
  number_cache_clusters         = local.enable_ha ? 2 : 1

  engine_version                = "6.x"
  // engine_version                = "6.0.5"
  // parameter_group_name          = "default.redis6.x.cluster.on"
  parameter_group_name          = "default.redis6.x"
  security_group_ids            = [ aws_security_group.redis_security_group.id ]

  snapshot_retention_limit      = 4

  apply_immediately             = true
}

// DNS zone
data "aws_route53_zone" "private_zone" {
  name         = var.route53_private_zone_name
  private_zone = true
}

// Main master DNS record
resource "aws_route53_record" "master" {
  zone_id                          = data.aws_route53_zone.private_zone.zone_id
  name                             = "${terraform.workspace}.master.${local.short_name}"
  type                             = "CNAME"
  ttl                              = "60"
  records                          = [aws_elasticache_replication_group.redis.primary_endpoint_address]
}

// Replica DNS record
resource "aws_route53_record" "replica" {
  zone_id                          = data.aws_route53_zone.private_zone.zone_id
  name                             = "${terraform.workspace}.replica.${local.short_name}"
  type                             = "CNAME"
  ttl                              = "60"
  records                          = [aws_elasticache_replication_group.redis.reader_endpoint_address]
}
