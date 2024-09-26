// AWS Region
variable "region" {}

// Service info
variable "project_name" {}
variable "service_name" {}

// EC2 Instance
variable "instance_type" {}
variable "vpc_id" {}
variable "private_subnet_ids" { type = list(string) }
variable "key_pair_name" {}
variable "detailed_monitoring" { type = bool }
variable "workhours_only" { type = bool }

// SNS ( Notifications )
variable "sns_topic_arn" {}

// Manually managed SGs
variable "aux_security_groups" {
  type = list(string)
  default = []
}

// Remote Access Rules
variable "ingress_sg_rules" { type = list(map(string)) }

// Auto-scaling group
variable "min_nodes" {}
variable "max_nodes" {}
variable "desired_nodes" {}
variable "target_group_arn" { // If set, uses ELB health check
  type = string
  default = ""
}
variable "target_asg_cpu" {
  type = number
  default = 30.0
}

variable "instance_warmup_time" {
  type = number
  default = 180
}

variable "root_volume_size" {
  type = number
  default = 30
}
variable "root_volume_iops" {
  type = number
  default = 3000
}
variable "root_volume_throughput" { // MiBps
  type = number
  default = 125
}

variable "is_lb_target" { // Must be set true if target_group_arn* are used
  type = bool
  default = false
}
variable "target_group_arn_suffix" { // If set, autoscale by ALB req count (thresholds, below, should also be set)
  type = string
  default = ""
}
variable "alb_reqs_autoscale_steps" { // Steps need to be map of string->number, like: { "adjustment": 1, "lower": 4000, "upper": 5500 }
  type = list(map(number))
  default = []
}

// Launch Configuration
variable "user_data" {}

// TAGS
variable default_tags {
  type = map(string)
}
variable ec2_tags {
  type = map(string)
}
