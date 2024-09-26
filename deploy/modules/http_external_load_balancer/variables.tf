// AWS Region
variable "region" {}

// Service info
variable "project_name" {}
variable "service_name" {}

// AWS Instance
variable "vpc_id" {}
variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids" { type = list(string) }

// Manually managed SGs
variable "aux_security_groups" { type = list(string) }

// Remote Access
variable "ingress_cidr_rules" {
  type = list(map(string))
  default = []
}
variable "ingress_sg_rules" {
  type = list(map(string))
  default = []
}

// SNS ( Notifications )
variable "sns_topic_arn" {}

// Health Check
variable "healthcheck_url" {}
variable "slow_start" {
  type = number
  default = 30
}
variable "deregistration_delay" {
  type = number
  default = 15
}

// DNS
variable "route53_public_zone_name" {}
variable "route53_public_dns_entry_name" {}

// TAGS
variable default_tags { type = map(string) }
