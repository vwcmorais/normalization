#!/bin/bash
export APP_NAME="OpenResty for Role Normalization API (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME}"
/usr/local/openresty/nginx/sbin/nginx
