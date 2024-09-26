#!/bin/bash
export APP_NAME="Catho Role Normalization API (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME}"

export PYTHONPATH="/seek/role-normalization:$PYTHONPATH"

cd /seek/role-normalization/role_normalization/api

gunicorn --config /seek/environments/all/api_gunicorn_conf.py $@ api:app
