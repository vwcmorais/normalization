// AMI
data "aws_ami" "instance_ami" {
  most_recent = true

  filter {
    name   = "name"
    values = ["arm-aips-americas-docker-*"]
  }
  owners = ["476134685374"]
}

// ROLE
data "aws_iam_policy_document" "assume_role_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "module_role" {
  name               = "${var.project_name}-${var.service_name}-${terraform.workspace}-${var.region}"
  assume_role_policy = data.aws_iam_policy_document.assume_role_policy.json
}
resource "aws_iam_role_policy_attachment" "session-manager-policy-attachment" {
  role       = aws_iam_role.module_role.name
  policy_arn = "arn:aws:iam::476134685374:policy/catholabs-session-manager-policy"
}
resource "aws_iam_instance_profile" "module_instance_profile" {
  name = "${var.project_name}-${var.service_name}-${terraform.workspace}-${var.region}"
  role = aws_iam_role.module_role.name
}

// ROLE: Secret Manager Resources
data "aws_secretsmanager_secret" "old_api" {
  name = "role-normalization/RoleNormalizationApi/${terraform.workspace}"
}
data "aws_secretsmanager_secret" "abapi" {
  name = "role-normalization/AbTestApi/${terraform.workspace}"
}
data "aws_secretsmanager_secret" "mysql" {
  name = "role-normalization/MySQL/${terraform.workspace}"
}
data "aws_secretsmanager_secret" "rabbitmq" {
  name = "role-normalization/RabbitMQ/${terraform.workspace}"
}
data "aws_secretsmanager_secret" "api" {
  name = "role-normalization/api/${terraform.workspace}"
}

resource "aws_iam_role_policy" "ec2_role_policy" {
  name = "${var.project_name}-${var.service_name}-${terraform.workspace}-${var.region}-ec2"
  role = aws_iam_role.module_role.id

  policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "GetSecretsFromSM",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetResourcePolicy",
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret",
                "secretsmanager:ListSecretVersionIds"
            ],
            "Resource": [
                "${data.aws_secretsmanager_secret.old_api.arn}",
                "${data.aws_secretsmanager_secret.api.arn}",
                "${data.aws_secretsmanager_secret.abapi.arn}",
                "${data.aws_secretsmanager_secret.mysql.arn}",
                "${data.aws_secretsmanager_secret.rabbitmq.arn}"
            ]
        },
        {
            "Sid": "GetBuildVersionTags",
            "Effect": "Allow",
            "Action": "ec2:DescribeTags",
            "Resource": "*"
        },
        {
            "Sid": "SetBuildVersionTags",
            "Effect": "Allow",
            "Action": [
              "ec2:CreateTags",
              "ec2:DeleteTags"
            ],
            "Resource": "*",
            "Condition": {
              "StringEquals": {
                "ec2:InstanceProfile": "${aws_iam_instance_profile.module_instance_profile.arn}"
              }
            }
        },
        {
            "Effect": "Allow",
            "Action": [
                "ecr:GetAuthorizationToken"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:GetRepositoryPolicy",
                "ecr:DescribeRepositories",
                "ecr:ListImages",
                "ecr:DescribeImages",
                "ecr:BatchGetImage"
            ],
            "Resource": [
                "arn:aws:ecr:us-east-1:476134685374:repository/role-normalization",
                "arn:aws:ecr:us-east-1:476134685374:repository/catho-recommendation/ab-api"
            ]
        }
    ]
}
EOF
}

data "aws_kms_key" "secrets_key" {
  key_id = data.aws_secretsmanager_secret.api.kms_key_id
}
resource "aws_kms_grant" "secret_key_grant" {
  name              = "${var.project_name}-${var.service_name}-${terraform.workspace}-${var.region}"
  key_id            = data.aws_kms_key.secrets_key.id
  grantee_principal = aws_iam_role.module_role.arn
  operations        = ["Decrypt"]
}

// SECURITY GROUP
resource "aws_security_group" "ec2_security_group" {
  name        = "${var.project_name}-${var.service_name}-${terraform.workspace}-ec2"
  description = "Role Normalization ${var.service_name} EC2 Security Group - ${terraform.workspace}-${var.region}"
  vpc_id      = var.vpc_id
  dynamic "ingress" {
    for_each = var.ingress_sg_rules
    content {
      description     = "From SG ${ingress.value.security_group} to ${ingress.value.protocol} (${ingress.value.from_port}:${ingress.value.to_port})"
      from_port       = ingress.value.from_port
      to_port         = ingress.value.to_port
      protocol        = ingress.value.protocol
      security_groups = [ingress.value.security_group]
    }
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(
    var.default_tags,
    {
      "Name" = "${var.project_name}-${var.service_name}-${terraform.workspace}-ec2",
    }
  )
}

// LAUNCH CONFIGURATION
resource "aws_launch_configuration" "module_launch_config" {
  name_prefix                 = "${terraform.workspace}-${var.project_name}-${var.service_name}-"
  image_id                    = data.aws_ami.instance_ami.id
  instance_type               = var.instance_type
  enable_monitoring           = var.detailed_monitoring
  associate_public_ip_address = false
  key_name                    = var.key_pair_name
  security_groups             = concat([aws_security_group.ec2_security_group.id], var.aux_security_groups)
  iam_instance_profile        = aws_iam_instance_profile.module_instance_profile.name
  user_data = var.user_data
  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size
    iops = var.root_volume_iops
    throughput = var.root_volume_throughput
    delete_on_termination = true
  }
  lifecycle {
    create_before_destroy = true
  }
}

// AUTOSCALING GROUP
resource "aws_autoscaling_group" "module_asg" {
  name                  = "${var.project_name}-${var.service_name}-${terraform.workspace}"
  launch_configuration  = aws_launch_configuration.module_launch_config.name
  min_size              = var.min_nodes
  max_size              = var.max_nodes
  desired_capacity      = var.desired_nodes
  health_check_type     = length(var.target_group_arn) == 0 ? "EC2" : "ELB"
  health_check_grace_period = var.instance_warmup_time
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 100
      max_healthy_percentage = var.desired_nodes == 1 ? 200 : 150
      instance_warmup = var.instance_warmup_time
    }
    triggers = ["tag"]
  }
  target_group_arns     = length(var.target_group_arn) == 0 ? null : [var.target_group_arn]
  max_instance_lifetime = 345600 # 4 days
  termination_policies  = [ "OldestLaunchConfiguration", "OldestInstance", "OldestLaunchTemplate", "Default" ]
  vpc_zone_identifier   = var.private_subnet_ids
  enabled_metrics       = [ "GroupDesiredCapacity", "GroupInServiceCapacity", "GroupInServiceInstances", "GroupTotalInstances" ]
  dynamic "tag" {
    for_each = merge(
      var.default_tags,
      var.ec2_tags,
      { "Name" = "${terraform.workspace}-${var.project_name}-${var.service_name}" }
    )
    content {
      key = tag.key
      value = tag.value
      propagate_at_launch = true
    }
  }
  lifecycle {
    create_before_destroy = true
  }
}

// AUTOSCALING POLICIES
resource "aws_autoscaling_schedule" "workhours_startup" {
  count                  = var.workhours_only ? 1 : 0
  scheduled_action_name  = "workhours_startup"
  min_size               = var.min_nodes
  max_size               = var.max_nodes
  desired_capacity       = var.desired_nodes
  recurrence             = "0 12 * * mon-fri"
  autoscaling_group_name = aws_autoscaling_group.module_asg.name
}

resource "aws_autoscaling_schedule" "workhours_shutdown" {
  count                  = var.workhours_only ? 1 : 0
  scheduled_action_name  = "workhours_shutdown"
  min_size               = 0
  max_size               = 0
  desired_capacity       = 0
  recurrence             = "0 1 * * tue-sat"
  autoscaling_group_name = aws_autoscaling_group.module_asg.name
}

// CPU intensive (workers) use this:
resource "aws_autoscaling_policy" "cpu_usage_scaling" {
  count                     = var.is_lb_target ? 1 : 0
  name                      = "${var.project_name}-${var.service_name}-${terraform.workspace}-cpu_usage_scaling"
  estimated_instance_warmup = var.instance_warmup_time
  autoscaling_group_name    = aws_autoscaling_group.module_asg.name
  policy_type               = "TargetTrackingScaling"
  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = var.target_asg_cpu
  }
}

// APIs use this:
resource "aws_autoscaling_policy" "alb_reqs_step_scaling" {
  count                     = var.is_lb_target ? 1 : 0
  name                      = "${var.project_name}-${var.service_name}-${terraform.workspace}-alb_reqs_step_scaling"
  autoscaling_group_name    = aws_autoscaling_group.module_asg.name
  policy_type               = "StepScaling"
  adjustment_type           = "ExactCapacity"
  dynamic "step_adjustment" {
    for_each = var.alb_reqs_autoscale_steps
    iterator = step
    content {
      scaling_adjustment          = var.min_nodes + step.value["adjustment"]
      metric_interval_lower_bound = lookup(step.value, "lower", null)
      metric_interval_upper_bound = lookup(step.value, "upper", null)
    }
  }
}

// AUTOSCALING ALARMS
resource "aws_cloudwatch_metric_alarm" "alb_reqs_step_scaling" {
  count                     = var.is_lb_target ? 1 : 0
  alarm_description         = "ALB request count alarm to ASG step scaling"
  alarm_name                = "${var.project_name}-${var.service_name}-${terraform.workspace}-request_count_scaling"
  comparison_operator       = "GreaterThanThreshold"
  evaluation_periods        = "1"
  metric_name               = "RequestCountPerTarget"
  namespace                 = "AWS/ApplicationELB"
  period                    = "300"
  statistic                 = "SampleCount"
  threshold                 = var.alb_reqs_autoscale_steps[0]["upper"]
  dimensions                = {
    TargetGroup = var.target_group_arn_suffix
  }
  actions_enabled           = "true"
  alarm_actions             = [aws_autoscaling_policy.alb_reqs_step_scaling[count.index].arn]
  ok_actions                = [aws_autoscaling_policy.alb_reqs_step_scaling[count.index].arn]
}

// MESSAGE ALARMS
resource "aws_cloudwatch_metric_alarm" "cpu_alarm" {
  count                     = var.detailed_monitoring ? 1 : 0
  alarm_description         = "High AutoScalingGroup EC2 average instance cpu usage"
  alarm_name                = "${var.project_name}-${var.service_name}-${terraform.workspace}-cpu_usage"
  comparison_operator       = "GreaterThanOrEqualToThreshold"
  evaluation_periods        = "5"
  metric_name               = "CPUUtilization"
  namespace                 = "AWS/EC2"
  period                    = "300"
  statistic                 = "Average"
  threshold                 = "85"
  alarm_actions             = [var.sns_topic_arn]
  insufficient_data_actions = [var.sns_topic_arn]
  dimensions                = {AutoScalingGroupName = aws_autoscaling_group.module_asg.name}
  tags                      = var.default_tags
}

resource "aws_cloudwatch_metric_alarm" "mem_alarm" {
  count                     = var.detailed_monitoring ? 1 : 0
  alarm_description         = "High AutoScalingGroup EC2 average memory usage"
  alarm_name                = "${var.project_name}-${var.service_name}-${terraform.workspace}-mem_usage"
  comparison_operator       = "GreaterThanOrEqualToThreshold"
  evaluation_periods        = "1"
  metric_name               = "mem_used_percent"
  namespace                 = "CWAgent"
  period                    = "300"
  statistic                 = "Average"
  threshold                 = "90"
  dimensions                = {AutoScalingGroupName = aws_autoscaling_group.module_asg.name}
  actions_enabled           = "true"
  alarm_actions             = [var.sns_topic_arn]
  insufficient_data_actions = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "swap_alarm" {
  count                     = var.detailed_monitoring ? 1 : 0
  alarm_description         = "High AutoScalingGroup EC2 average swap usage"
  alarm_name                = "${var.project_name}-${var.service_name}-${terraform.workspace}-swap_usage"
  comparison_operator       = "GreaterThanOrEqualToThreshold"
  evaluation_periods        = "1"
  metric_name               = "swap_used_percent"
  namespace                 = "CWAgent"
  period                    = "300"
  statistic                 = "Average"
  threshold                 = "10"
  dimensions                = {AutoScalingGroupName = aws_autoscaling_group.module_asg.name}
  actions_enabled           = "true"
  alarm_actions             = [var.sns_topic_arn]
  insufficient_data_actions = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "root_disk_alarm" {
  count                     = var.detailed_monitoring ? 1 : 0
  alarm_description         = "High EC2 root disk utilization"
  alarm_name                = "${var.project_name}-${var.service_name}-${terraform.workspace}-root_disk_usage"
  comparison_operator       = "GreaterThanOrEqualToThreshold"
  evaluation_periods        = "1"
  metric_name               = "disk_used_percent"
  namespace                 = "CWAgent"
  period                    = "300"
  statistic                 = "Average"
  threshold                 = "80"
  dimensions                = {
    AutoScalingGroupName = aws_autoscaling_group.module_asg.name,
  }
  actions_enabled           = "true"
  alarm_actions             = [var.sns_topic_arn]
  insufficient_data_actions = [var.sns_topic_arn]
}

output "security_group_id" {
  value = aws_security_group.ec2_security_group.id
}

output "role_name" {
  value = aws_iam_role.module_role.name
}

