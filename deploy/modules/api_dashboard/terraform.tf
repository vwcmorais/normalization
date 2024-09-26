resource "aws_cloudwatch_dashboard" "metrics_dashboard" {
  count          = var.detailed_monitoring ? 1 : 0
  dashboard_name = "${var.project_name}-${var.service_name}-${terraform.workspace}"
  dashboard_body = <<-EOT
{
    "widgets": [
        {
            "type": "metric",
            "x": 0,
            "y": 0,
            "width": 24,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                  [ "AWS/ApplicationELB", "RequestCount", "TargetGroup", "${var.target_group_arn_suffix}", "LoadBalancer", "${var.load_balancer_arn_suffix}" ]
                ],
                "region": "${var.region}",
                "title": "Requests",
                "period": 300,
                "stat": "Sum"
            }
        },
        {
            "type": "metric",
            "x": 12,
            "y": 6,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {AWS/EC2,AutoScalingGroupName} MetricName=\"CPUUtilization\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)" } ]
                ],
                "region": "${var.region}",
                "title": "CPU Utilization",
                "period": 300
            }
        },
        {
            "type": "metric",
            "x": 0,
            "y": 6,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                  [ "AWS/ApplicationELB", "HTTPCode_Target_3XX_Count", "TargetGroup", "${var.target_group_arn_suffix}", "LoadBalancer", "${var.load_balancer_arn_suffix}" ],
                  [ "AWS/ApplicationELB", "HTTPCode_Target_4XX_Count", "TargetGroup", "${var.target_group_arn_suffix}", "LoadBalancer", "${var.load_balancer_arn_suffix}" ],
                  [ "AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "TargetGroup", "${var.target_group_arn_suffix}", "LoadBalancer", "${var.load_balancer_arn_suffix}" ]
                ],
                "region": "${var.region}",
                "title": "3xx/4xx/5xx responses",
                "period": 300,
                "stat": "Sum"
            }
        },
        {
            "type": "metric",
            "x": 0,
            "y": 12,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"mem_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)", "label": "Average" } ],
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"mem_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Maximum', 300)", "label": "Maximum" } ],
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"mem_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Minimum', 300)", "label": "Minimum" } ]
                ],
                "region": "${var.region}",
                "title": "Memory Utilization"
            }
        },
        {
            "type": "metric",
            "x": 12,
            "y": 12,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"swap_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)", "label": "Average" } ],
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"swap_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Maximum', 300)", "label": "Maximum" } ],
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"swap_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Minimum', 300)", "label": "Minimum" } ]
                ],
                "region": "${var.region}",
                "title": "Swap Utilization"
            }
        },
        {
            "type": "metric",
            "x": 0,
            "y": 18,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {AWS/AutoScaling,AutoScalingGroupName} MetricName=\"GroupInServiceInstances\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Minimum', 60)" } ]
                ],
                "region": "${var.region}",
                "title": "InService Instances"
            }
        },
        {
            "type": "metric",
            "x": 12,
            "y": 18,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {AWS/EC2,AutoScalingGroupName} MetricName=\"NetworkIn\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)" } ],
                    [ { "expression": "SEARCH(' {AWS/EC2,AutoScalingGroupName} MetricName=\"NetworkOut\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)" } ]
                ],
                "region": "${var.region}",
                "title": "Network In/Out"
            }
        },
        {
            "type": "metric",
            "x": 0,
            "y": 24,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {AWS/EC2,AutoScalingGroupName} MetricName=\"EBSReadOps\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)" } ],
                    [ { "expression": "SEARCH(' {AWS/EC2,AutoScalingGroupName} MetricName=\"EBSWriteOps\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)" } ]
                ],
                "region": "${var.region}",
                "title": "EBS Write/Read Ops"
            }
        },
        {
            "type": "metric",
            "x": 12,
            "y": 24,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {AWS/EC2,AutoScalingGroupName} MetricName=\"EBSReadBytes\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)" } ],
                    [ { "expression": "SEARCH(' {AWS/EC2,AutoScalingGroupName} MetricName=\"EBSWriteBytes\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)" } ]
                ],
                "region": "${var.region}",
                "title": "EBS Write/Read Bytes"
            }
        },
        {
            "type": "metric",
            "x": 0,
            "y": 30,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"disk_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)", "label": "Average" } ],
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"disk_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Minimum', 300)", "label": "Minimum" } ],
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"disk_used_percent\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Maximum', 300)", "label": "Maximum" } ]
                ],
                "region": "${var.region}",
                "title": "Root Disk Utilization"
            }
        },
        {
            "type": "metric",
            "x": 12,
            "y": 30,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": false,
                "metrics": [
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"processes_running\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Average', 300)", "label": "Average" } ],
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"processes_running\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Minimum', 300)", "label": "Minimum" } ],
                    [ { "expression": "SEARCH(' {CWAgent,AutoScalingGroupName} MetricName=\"processes_running\" AutoScalingGroupName=${var.project_name}-${var.service_name}-${terraform.workspace}-* ', 'Maximum', 300)", "label": "Maximum" } ]
                ],
                "region": "${var.region}",
                "title": "Running processes"
            }
        }
   ]
}
EOT
}
