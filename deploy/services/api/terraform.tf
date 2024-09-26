terraform {
  required_version = "~> 1.0"
  backend "s3" {
    encrypt              = true
    bucket               = "catholabs-terraform-state"
    workspace_key_prefix = "role-normalization"
    key                  = "api"
    region               = "us-east-1"
  }
}

provider "aws" {
  region = var.region
}

locals {

  instance_startup_limit = 240

  ab_api_image_download = <<EOF
echo "AB Test API enabled - Downloading AB API image (${var.ab_api_image})"
docker pull ${var.ab_api_image}
EOF

  ab_api_start = <<EOF
echo "AB Test API enabled - Starting AB API container"
docker run -d \
    --name ab-api \
    --restart always \
    --network api \
    --log-opt "max-size=50m" \
    --log-opt "max-file=1" \
    -e API_PORT="81" \
    -e APPNAME="catho-ab-rolenorm" \
    -e REDIS_CONFIG="${terraform.workspace}.${var.region}.primary.ab.redis.rolenorm.${var.route53_private_zone_name}|6379|" \
    -e ABTEST_CONFIG="role_norm|nginx:80|0" \
    -e AUTH_METHOD="SECRET_MANAGER" \
    -e SECRET_MANAGER_CONFIG="role-normalization/AbTestApi/${terraform.workspace}|${var.region}" \
    -e AWS_DEFAULT_REGION="${var.region}" \
    --health-cmd "curl --fail http://127.0.0.1:81/healthcheck || exit 1" \
    --ulimit nofile=65536:65536 \
    -p '81:81' \
    ${var.ab_api_image}
EOF

}

// TODO: Add security group rule to RabbitMQ

// RecSys base resources ( needed to SG rules )
data "terraform_remote_state" "recsys" {
  backend = "s3"
  config = {
    encrypt              = true
    bucket               = "catholabs-terraform-state"
    workspace_key_prefix = "recommendation"
    key                  = "base"
    region               = "us-east-1"
  }
  workspace = terraform.workspace
}

// Access to RabbitMQ (routine enqueues normalized candidates to be reindexed)
resource "aws_security_group_rule" "rabbitmq" {
  security_group_id        = data.terraform_remote_state.recsys.outputs.security_groups["rabbitmq"]
  description              = "Allows from Role Normalization SG - Managed by terraform"
  type                     = "ingress"
  from_port                = 5672
  to_port                  = 5672
  protocol                 = "tcp"
  source_security_group_id = module.autoscaling_group.security_group_id
}

module "autoscaling_group" {
  source              = "../../modules/autoscaling_group"
  region              = var.region
  project_name        = var.project_name
  service_name        = "api"
  instance_type       = var.api_instance_type
  vpc_id              = var.vpc_id
  private_subnet_ids  = var.private_subnet_ids
  key_pair_name       = var.key_pair_name
  detailed_monitoring = var.detailed_monitoring
  workhours_only      = var.workhours_only
  sns_topic_arn       = var.sns_topic_arn
  instance_warmup_time = local.instance_startup_limit
  ingress_sg_rules = [{
    security_group = module.load_balancer.security_group_id
    protocol       = "TCP",
    from_port      = 80,
    to_port        = 80
  }]
  min_nodes                         = var.api_asg_min_nodes
  max_nodes                         = var.api_asg_max_nodes
  desired_nodes                     = var.api_asg_desired_nodes
  is_lb_target                      = true
  target_group_arn                  = module.load_balancer.target_group_arn
  target_group_arn_suffix           = module.load_balancer.target_group_arn_suffix
  alb_reqs_autoscale_steps          = [
    {
      adjustment = 0
      upper      = 12000
    },
    {
      adjustment = 1
      lower      = 12000
      upper      = 20000
    },
    {
      adjustment = 2
      lower      = 20000
    }
  ]
  user_data = templatefile("${path.module}/files/userdata.sh",
    {
      region                = var.region
      secret_id             = "role-normalization/api/${terraform.workspace}"
      environment           = terraform.workspace
      default_build_version = var.api_build_version
      docker_image_prefix   = var.docker_image_prefix
      filebeat_image        = var.filebeat_image
      logstash_endpoint     = var.logstash_endpoint
      nginx_error_log_group = aws_cloudwatch_log_group.nginx_error_log_group.name
      start_cwagent         = var.detailed_monitoring ? "systemctl start amazon-cloudwatch-agent.service && systemctl enable amazon-cloudwatch-agent.service" : ""
      enable_profiling      = var.api_enable_profiling ? "true" : "false"
      ab_api_image_download = var.enable_ab_api ? local.ab_api_image_download : "echo 'AB API disabled - not downloading image'"
      ab_api_start          = var.enable_ab_api ? local.ab_api_start : "echo 'AB API disabled - not starting container'"
    }
  )
  default_tags = merge(
    var.default_tags,
    {
      "Service"     = "api",
      "Environment" = terraform.workspace,
    }
  )
  ec2_tags = {
    "BuildVersion" = var.api_build_version
    "FalconTags"   = "catho,seek-ai,aws,safe,ec2,spot,docker,nginx,wsgi,python,${var.falcon_tags}"
  }
}

module "load_balancer" {
  source                        = "../../modules/http_external_load_balancer"
  region                        = var.region
  project_name                  = var.project_name
  service_name                  = "api"
  vpc_id                        = var.vpc_id
  private_subnet_ids            = var.private_subnet_ids
  public_subnet_ids             = var.public_subnet_ids
  aux_security_groups           = [var.catho_external_access_security_group_id, var.team_access_security_group_id]
  sns_topic_arn                 = var.sns_topic_arn
  route53_public_zone_name      = var.route53_public_zone_name
  route53_public_dns_entry_name = "${terraform.workspace}.${var.region}.api.rolenormalization"
  healthcheck_url               = "/healthcheck"
  default_tags = merge(
    var.default_tags,
    {
      "Service"     = "api",
      "Environment" = terraform.workspace,
    }
  )
}

module "api_dashboard" {
  source                   = "../../modules/api_dashboard"
  region                   = var.region
  project_name             = var.project_name
  service_name             = "api"
  detailed_monitoring      = var.detailed_monitoring
  load_balancer_arn_suffix = module.load_balancer.load_balancer_arn_suffix
  target_group_arn_suffix  = module.load_balancer.target_group_arn_suffix
}

resource "aws_cloudwatch_log_group" "nginx_error_log_group" {
  name              = "/${var.project_name}/api/${terraform.workspace}/nginx_error"
  retention_in_days = 7
  tags              = merge(var.default_tags, { "Name" = "/${var.project_name}/api/${terraform.workspace}/nginx_error" })
}

output "ec2_security_group" {
  value = module.autoscaling_group.security_group_id
}

output "role_name" {
  value = module.autoscaling_group.role_name
}
