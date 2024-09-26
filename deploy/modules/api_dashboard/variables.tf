// AWS Region
variable "region" {}

// Service info
variable "project_name" {}
variable "service_name" {}
variable "target_group_arn_suffix" {}
variable "load_balancer_arn_suffix" {}

// Enable/Disable
variable "detailed_monitoring" {
  type = bool
  default = false
}
