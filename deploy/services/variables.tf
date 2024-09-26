// AWS Region
variable "region" {}

// AWS Instance
variable "vpc_id" {}
variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids" { type = list(string) }
variable "key_pair_name" {}

// Manually managed SGs
variable "catho_external_access_security_group_id" {}
variable "team_access_security_group_id" {}

// Environment Dependent Falcon Tags
variable "falcon_tags" {}

// Project
variable "project_name" { default = "role-normalization" }

// Docker image ID (includes registry)
variable "docker_image_prefix" { type = string } // Should not include version
variable "filebeat_image" { type = string }
variable "ab_api_image" { type = string }

// Stack conf
variable "detailed_monitoring" { type = bool }
variable "workhours_only" { type = bool }

// SNS ( Notifications )
variable "sns_topic_arn" {}

// DNS
variable "route53_private_zone_name" {}
variable "route53_public_zone_name" {}

// API parameters
variable "api_build_version" {}
variable "api_instance_type" {}
variable "api_asg_min_nodes" {}
variable "api_asg_max_nodes" {}
variable "api_asg_desired_nodes" {}
variable "api_enable_profiling" {
  type = bool
  default = false
}

// Routing parameters
variable "routine_instance_type" {}

// AB Tests API
variable "enable_ab_api" {
  type = bool
  default = false
}

// TAGS
variable default_tags {
  type = map(string)
  default = {
    "Application"          = "CathoRoleNormalization"
    "Brand"                = "CATHO"
    "BusinessUnit"         = "APnA"
    "ApplicationRole"      = "API"
    "Domain"               = "Recommendation"
    "Managed_by_Terraform" = "true"
    "Owner"                = "americas.aips@seek.com.au"
    "Project"              = "RoleNormalization"
    "Team"                 = "AIPS-AMERICAS"
  }
}

// Logstash 
variable "logstash_endpoint" {}
