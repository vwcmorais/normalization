#!/bin/bash
export APP_NAME="Catho Work Experience Role Normalization Routine - sleep 3 hours and then run every 9 hours (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME}"

sleep $((3*60*60)) && /seek/entrypoints/util/run_each.sh $((9*60*60)) /seek/entrypoints/normalize_user_work_exp_roles.sh
