terraform {
  required_version = "~> 1.0"
  backend "s3" {
    encrypt              = true
    bucket               = "catholabs-terraform-state"
    workspace_key_prefix = "role-normalization"
    key                  = "routines"
    region               = "us-east-1"
  }
}

provider "aws" {
  region = var.region
}

locals {
  service_name = "routines"

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

// API resources ( we use API SG )
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

data "aws_ami" "instance_ami" {
  most_recent = true
  filter {
    name   = "name"
    values = ["arm-aips-americas-docker-*"]
  }
  owners = ["476134685374"]
}

resource "aws_iam_instance_profile" "routine" {
  name     = "${terraform.workspace}-${var.region}-${var.project_name}-${local.service_name}"
  role     = data.terraform_remote_state.api.outputs.role_name
}

resource "aws_instance" "main" {
  ami                    = data.aws_ami.instance_ami.id
  instance_type          = var.routine_instance_type
  subnet_id              = var.private_subnet_ids[0]
  iam_instance_profile   = aws_iam_instance_profile.routine.name
  vpc_security_group_ids = [data.terraform_remote_state.api.outputs.ec2_security_group]
  monitoring             = var.detailed_monitoring
  key_name               = var.key_pair_name
  user_data = templatefile("${path.module}/files/userdata.sh",
    {
      region                = var.region
      secret_id             = "role-normalization/api/${terraform.workspace}"
      environment           = terraform.workspace
      default_build_version = var.api_build_version
      docker_image_prefix   = var.docker_image_prefix
      start_cwagent         = var.detailed_monitoring ? "systemctl start amazon-cloudwatch-agent.service && systemctl enable amazon-cloudwatch-agent.service" : ""
      ab_api_image_download = var.enable_ab_api ? local.ab_api_image_download : "echo 'AB API disabled - not downloading image'"
      ab_api_start          = var.enable_ab_api ? local.ab_api_start : "echo 'AB API disabled - not starting container'"
    }
  )
  user_data_replace_on_change = true
  ebs_optimized          = true
  tags        = merge(
    var.default_tags,
    {
      "Name" = "${terraform.workspace}-${var.project_name}-${local.service_name}",
      "ReleaseVersion" = var.api_build_version,
      "FalconTags"   = "catho,seek-ai,aws,safe,ec2,spot,docker,python,${var.falcon_tags}",
      "Service"     = local.service_name,
      "Environment" = terraform.workspace,
      "BuildVersion" = var.api_build_version,
    }
  )
  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    throughput = 125
    iops = 3000
    delete_on_termination = true
  }
  // lifecycle {
  //   ignore_changes = [ ami ]
  //   prevent_destroy = true
  // }
}
