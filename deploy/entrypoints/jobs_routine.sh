#!/bin/bash
export APP_NAME="Catho Job Role Normalization Routine - sleep 6 hours and then run every 9 hours (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME}"

sleep $((6*60*60)) && /seek/entrypoints/util/run_each.sh $((9*60*60)) /seek/entrypoints/normalize_job_roles.sh
