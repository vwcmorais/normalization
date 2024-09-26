// AWS Region
region = "us-east-1"

// AWS Instance
vpc_id             = "vpc-08442d93529373355"
private_subnet_ids = ["subnet-0e5be4d0720baf534", "subnet-002d696c30cc767db"]
public_subnet_ids  = ["subnet-0bf78188ed76befdf", "subnet-0d86cd0451956a329"]
key_pair_name      = "catho-recommendation-staging"

// External SGs
catho_external_access_security_group_id = "sg-0034c0de6a2e1253a" // catho-external-access
team_access_security_group_id = "sg-06a658f49443d01a4" // aips_americas_team_access

// Environment-dependent falcon tags
// Security level ( high, medium, low ), environment
falcon_tags = "low,staging"

// Docker image IDs
docker_image_prefix = "476134685374.dkr.ecr.us-east-1.amazonaws.com/role-normalization"
filebeat_image = "476134685374.dkr.ecr.us-east-1.amazonaws.com/role-normalization:filebeat-arm"
ab_api_image = "476134685374.dkr.ecr.us-east-1.amazonaws.com/catho-recommendation/ab-api:1"

// Stack conf
detailed_monitoring = false
workhours_only = true
enable_ab_api = false

// SNS ( Notifications )
sns_topic_arn = "arn:aws:sns:us-east-1:476134685374:catho-recommendation-staging"

// DNS
route53_public_zone_name = "catholabs.com"
route53_private_zone_name = "catholabs.aws"

// API parameters
api_build_version = "main-297"
api_asg_min_nodes = 1
api_asg_max_nodes = 1
api_asg_desired_nodes = 1
api_instance_type = "t4g.medium"
api_enable_profiling = false

routine_instance_type = "t3.small"

// TAGS

default_tags = {
  "Application"          = "RoleNormalization"
  "Brand"                = "CATHO"
  "BusinessUnit"         = "APnA"
  "ApplicationRole"      = "API"
  "Domain"               = "Recommendation"
  "Environment"          = "Staging"
  "Managed_by_Terraform" = "true"
  "Owner"                = "americas.aips@seek.com.au"
  "Project"              = "RoleNormalization"
  "Team"                 = "AIPS-AMERICAS"
}

// LOGSTASH_ENDPOINT
logstash_endpoint = "logstash.develop.loglake.catholabs.com:5044"
