#!/bin/bash
export APP_NAME="Catho CV Role Normalization Routine - run every 9 hours (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME}"

/seek/entrypoints/util/run_each.sh $((9*60*60)) /seek/entrypoints/normalize_user_cv_roles.sh
