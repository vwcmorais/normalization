#!/bin/bash
export APP_NAME="Catho User Work Experiences Role Normalization Routine - normalize work experience roles (${DEPLOY_ENVIRONMENT})"

echo "Starting ${APP_NAME}"

export PYTHONPATH="/seek/role-normalization:$PYTHONPATH"
python3 /seek/role-normalization/role_normalization/routine/users_role_norm.py --norm-type work_exp
