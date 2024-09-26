data "aws_vpc" "module_vpc" {
  id = var.vpc_id
}

data "aws_nat_gateway" "private_gw" {
  count = length( var.public_subnet_ids )
  subnet_id = var.public_subnet_ids[count.index]
}

resource "aws_security_group" "lb_security_group" {
  name        = "${var.project_name}-${var.service_name}-${terraform.workspace}-lb"
  description = "Catho Role Normalization ${var.service_name} ALB Security Group - ${terraform.workspace}"
  vpc_id      = var.vpc_id
  dynamic "ingress" {
    for_each = var.ingress_cidr_rules
    content {
      description     = "From CIDR ${ingress.value.cidr_block} to ${ingress.value.protocol} (${ingress.value.from_port}:${ingress.value.to_port})"
      from_port       = ingress.value.from_port
      to_port         = ingress.value.to_port
      protocol        = ingress.value.protocol
      cidr_blocks     = [ingress.value.cidr_block]
    }
  }
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
  dynamic "ingress" {
    for_each = data.aws_nat_gateway.private_gw
    iterator = gw
    content {
      description = "From private NAT Gateway to HTTP"
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_blocks = ["${gw.value.public_ip}/32"]
    }
  }
  dynamic "ingress" {
    for_each = data.aws_nat_gateway.private_gw
    iterator = gw
    content {
      description = "From private NAT Gateway to HTTPS"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["${gw.value.public_ip}/32"]
    }
  }
  egress {
    description = "Load Balancer connections to EC2"
    protocol    = "tcp"
    from_port   = 80
    to_port     = 80
    cidr_blocks = [data.aws_vpc.module_vpc.cidr_block]
  }
  tags = merge(var.default_tags, { "Name" = "${var.project_name}-${var.service_name}-${terraform.workspace}-lb" })
}

resource "aws_lb" "module_lb" {
  name            = "role-normalization-${replace(var.service_name, "_", "-")}-${terraform.workspace}"
  internal        = false
  subnets         = var.public_subnet_ids
  security_groups = concat([aws_security_group.lb_security_group.id], var.aux_security_groups)
  tags            = merge(var.default_tags, { "Name" = "${var.project_name}-${var.service_name}-${terraform.workspace}" })
}

resource "aws_lb_listener" "front_end" {
  load_balancer_arn = aws_lb.module_lb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = aws_acm_certificate.app.arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.module_tg.arn
  }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener" "module_listener" {
  load_balancer_arn = aws_lb.module_lb.arn
  port              = "80"
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.module_tg.arn
  }
  lifecycle {
    create_before_destroy = true
  }
}
resource "aws_lb_target_group" "module_tg" {
  name                 = "role-normalization-${replace(var.service_name, "_", "-")}-${terraform.workspace}"
  port                 = "80"
  protocol             = "HTTP"
  vpc_id               = var.vpc_id
  slow_start           = var.slow_start
  deregistration_delay = var.deregistration_delay
  health_check {
    healthy_threshold   = 5
    unhealthy_threshold = 2
    timeout             = 2
    interval            = 10
    matcher             = "200" // Success codes
    path                = var.healthcheck_url
  }
  lifecycle {
    create_before_destroy = true
  }
  tags = merge(var.default_tags, { "Name" = "${var.project_name}-${var.service_name}-${terraform.workspace}" })
}

resource "aws_acm_certificate" "app" {
  domain_name       = "${var.route53_public_dns_entry_name}.${data.aws_route53_zone.public_zone.name}"
  validation_method = "DNS"
  tags = merge(
    var.default_tags,
    { "Name" = "${var.route53_public_dns_entry_name}.${data.aws_route53_zone.public_zone.name}" }
  )
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "cert_challenge" {
  for_each = {
    for dvo in aws_acm_certificate.app.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }
  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.public_zone.zone_id
}

data "aws_route53_zone" "public_zone" {
  name         = var.route53_public_zone_name
  private_zone = false
}

resource "aws_route53_record" "public_cname" {
  zone_id = data.aws_route53_zone.public_zone.zone_id
  name    = var.route53_public_dns_entry_name
  type    = "CNAME"
  ttl     = "60"
  records = [aws_lb.module_lb.dns_name]
}
resource "aws_cloudwatch_metric_alarm" "http_5xx_status_count" {
  alarm_description   = "High number of 5xx response status"
  alarm_name          = "${var.project_name}-${var.service_name}-${terraform.workspace}-http_5xx_status_count"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "2"
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "100"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]
  ok_actions          = [var.sns_topic_arn]
  dimensions          = {LoadBalancer = aws_lb.module_lb.arn_suffix}
  tags                = var.default_tags
}

resource "aws_cloudwatch_metric_alarm" "response_time" {
  alarm_description   = "High average response time"
  alarm_name          = "${var.project_name}-${var.service_name}-${terraform.workspace}-response_time"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "2"
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = "300"
  statistic           = "Average"
  threshold           = "100"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]
  ok_actions          = [var.sns_topic_arn]
  dimensions          = {LoadBalancer = aws_lb.module_lb.arn_suffix}
  tags                = var.default_tags
}

resource "aws_cloudwatch_metric_alarm" "connection_error_count" {
  alarm_description   = "High connection error count"
  alarm_name          = "${var.project_name}-${var.service_name}-${terraform.workspace}-connection_error_count"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "2"
  metric_name         = "TargetConnectionErrorCount"
  namespace           = "AWS/ApplicationELB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "100"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.sns_topic_arn]
  ok_actions          = [var.sns_topic_arn]
  dimensions          = {LoadBalancer = aws_lb.module_lb.arn_suffix}
  tags                = var.default_tags
}

output "security_group_id" {
  value = aws_security_group.lb_security_group.id
}
output "target_group_arn" {
  value = aws_lb_target_group.module_tg.arn
}
output "target_group_arn_suffix" {
  value = aws_lb_target_group.module_tg.arn_suffix
}
output "load_balancer_arn_suffix" {
  value = aws_lb.module_lb.arn_suffix
}
