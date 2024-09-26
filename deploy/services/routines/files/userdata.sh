#!/usr/bin/env bash

systemctl start docker.service
systemctl enable docker.service

export AWS_DEFAULT_REGION="${region}"

eval $(aws ecr get-login --no-include-email --region us-east-1)
docker pull ${docker_image_prefix}:${default_build_version}

${ab_api_image_download}

echo 'Creating docker network'
docker network create rolenorm

${ab_api_start}

IMAGE_VERSION=$( docker image inspect ${docker_image_prefix}:${default_build_version} | jq -r '.[0].Config.Labels.BuildVersion' | awk '{printf $1}' )
INSTANCE_ID="$(ec2-metadata -i | cut -d ':' -f 2 | awk '{printf $1}')"
aws ec2 create-tags --resources "$${INSTANCE_ID}" --tags "Key=BuildVersion,Value=$${IMAGE_VERSION}"

${start_cwagent}

echo "Role Normalization User CVs Routine Container"
docker run -d \
    --name user_cvs_routine \
    --restart always \
    --network rolenorm \
    --log-opt "max-size=50m" \
    --log-opt "max-file=1" \
    -e DEPLOY_ENVIRONMENT="${environment}" \
    -e ROLE_NORM_ENV="${environment}" \
    -e SECRET_MANAGER_CONFIG="${secret_id}|${region}" \
    -e AWS_DEFAULT_REGION="${region}" \
    --no-healthcheck \
    ${docker_image_prefix}:${default_build_version} \
    entrypoints/user_cvs_routine.sh

echo "Role Normalization User Work Experiences Routine Container"
docker run -d \
    --name user_work_exps_routine \
    --restart always \
    --network rolenorm \
    --log-opt "max-size=50m" \
    --log-opt "max-file=1" \
    -e DEPLOY_ENVIRONMENT="${environment}" \
    -e ROLE_NORM_ENV="${environment}" \
    -e SECRET_MANAGER_CONFIG="${secret_id}|${region}" \
    -e AWS_DEFAULT_REGION="${region}" \
    --no-healthcheck \
    ${docker_image_prefix}:${default_build_version} \
    entrypoints/user_work_exps_routine.sh

echo "Role Normalization Jobs Routine Container"
docker run -d \
    --name jobs_routine \
    --restart always \
    --network rolenorm \
    --log-opt "max-size=50m" \
    --log-opt "max-file=1" \
    -e DEPLOY_ENVIRONMENT="${environment}" \
    -e ROLE_NORM_ENV="${environment}" \
    -e SECRET_MANAGER_CONFIG="${secret_id}|${region}" \
    -e AWS_DEFAULT_REGION="${region}" \
    --no-healthcheck \
    ${docker_image_prefix}:${default_build_version} \
    entrypoints/jobs_routine.sh

init_falcon_agent.sh
