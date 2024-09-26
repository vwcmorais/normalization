#!/bin/bash
export APP_NAME="Catho User CVs Role Normalization Routine - normalize CV roles (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME}"

export PYTHONPATH="/seek/role-normalization:$PYTHONPATH"
python3 /seek/role-normalization/role_normalization/routine/users_role_norm.py --norm-type cv
