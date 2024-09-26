#!/usr/bin/env bash

systemctl start docker.service
systemctl enable docker.service

export AWS_DEFAULT_REGION="${region}"

eval $(aws ecr get-login --no-include-email --region us-east-1)
docker pull ${docker_image_prefix}:${default_build_version}

${ab_api_image_download}

echo 'Setting up Nginx log file'
echo > /var/log/nginx_error.log
chown 1111:1111 /var/log/nginx_error.log

echo 'Creating docker network'
docker network create api

echo 'Starting Role Normalization API Container'
docker run -d \
    --name api \
    --restart always \
    --network api \
    --log-opt "max-size=50m" \
    --log-opt "max-file=2" \
    -e DEPLOY_ENVIRONMENT="${environment}" \
    -e ROLE_NORM_ENV="${environment}" \
    -e SECRET_MANAGER_CONFIG="${secret_id}|${region}" \
    -e AWS_DEFAULT_REGION="${region}" \
    --health-cmd "curl --fail http://127.0.0.1:8192/healthcheck || exit 1" \
    --ulimit nofile=65536:65536 \
    ${docker_image_prefix}:${default_build_version} \
    entrypoints/api.sh

echo 'Starting Role Normalization Events API Container'
docker run -d \
    --name events_api \
    --restart always \
    --network api \
    --log-opt "max-size=50m" \
    --log-opt "max-file=2" \
    -e DEPLOY_ENVIRONMENT="${environment}" \
    -e ROLE_NORM_ENV="${environment}" \
    -e SECRET_MANAGER_CONFIG="${secret_id}|${region}" \
    -e AWS_DEFAULT_REGION="${region}" \
    --health-cmd "curl --fail http://127.0.0.1:8192/healthcheck || exit 1" \
    --ulimit nofile=65536:65536 \
    ${docker_image_prefix}:${default_build_version} \
    entrypoints/events_api.sh

echo 'Starting OpenResty (nginx) Container'
NGINX_ID=$( docker run -d \
    --name nginx \
    --restart always \
    --network api \
    --log-opt "max-size=500m" \
    --log-opt "max-file=1" \
    -e DEPLOY_ENVIRONMENT="${environment}" \
    --mount 'src=/var/log/nginx_error.log,target=/seek/logs/nginx_error.log,type=bind' \
    --ulimit nofile=65536:65536 \
    --user "root" \
    --health-cmd "curl --fail http://127.0.0.1:80/healthcheck || exit 1" \
    -p '80:80' \
    ${docker_image_prefix}:${default_build_version} \
    entrypoints/openresty.sh
)

${ab_api_start}

# FILEBEAT

echo 'Using: ${logstash_endpoint}'
mkdir -p /usr/share/filebeat
cat > /usr/share/filebeat/filebeat.yml << EOF

filebeat.inputs:
- type: docker
  combine_partial: true
  containers.ids:
    - '$${NGINX_ID}'
  json.message_key: log
  json.keys_under_root: true

processors:
    - drop_event:
        when:
          not:
            has_fields: ["appname"]

output.logstash:
    hosts: ["${logstash_endpoint}"]
    ssl.enabled: false

logging.level: info

EOF

echo 'Starting FileBeat Container'
docker run -d \
    --log-opt "max-size=50m" \
    --log-opt "max-file=2" \
    --name filebeat \
    --user=root \
    --ulimit nofile=65536:65536 \
    --restart always \
    -v /usr/share/filebeat/filebeat.yml:/usr/share/filebeat/filebeat.yml \
    -v /var/lib/docker/containers:/var/lib/docker/containers \
    -v /var/run/docker.sock:/var/run/docker.sock \
    ${filebeat_image} filebeat -e -strict.perms=false

IMAGE_VERSION=$( docker image inspect ${docker_image_prefix}:${default_build_version} | jq -r '.[0].Config.Labels.BuildVersion' | awk '{printf $1}' )
INSTANCE_ID="$(ec2-metadata -i | cut -d ':' -f 2 | awk '{printf $1}')"
aws ec2 create-tags --resources "$${INSTANCE_ID}" --tags "Key=BuildVersion,Value=$${IMAGE_VERSION}"

echo "Setting up Amazon Cloudwatch Agent to send error logs"
cat > /etc/amazon/amazon-cloudwatch-agent/amazon-cloudwatch-agent.d/nginx_error_logs.json <<EOF
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/nginx_error.log",
            "log_group_name": "${nginx_error_log_group}",
            "log_stream_name": "{instance_id}",
            "timestamp_format": "%Y/%m/%d %H:%M:%S",
            "timezone": "UTC",
            "multi_line_start_pattern": "{timestamp_format}",
            "auto_removal": true
          }
        ]
      }
    }
  }
}
EOF

${start_cwagent}

init_falcon_agent.sh
