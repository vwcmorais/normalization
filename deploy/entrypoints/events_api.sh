#!/bin/bash
export APP_NAME="Catho Role Normalization API - Events Endpoint (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME} - Events Endpoint"

export PYTHONPATH="/seek/role-normalization:$PYTHONPATH"

cd /seek/role-normalization/role_normalization/api

gunicorn --config /seek/environments/all/events_api_gunicorn_conf.py $@ events_api:app
