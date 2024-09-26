#!/bin/bash
export APP_NAME="Catho Jobs Role Normalization Routine - normalize job roles (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME}"

export PYTHONPATH="/seek/role-normalization:$PYTHONPATH"
python3 /seek/role-normalization/role_normalization/routine/jobs_role_norm.py
