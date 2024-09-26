#!/bin/bash

export PYTHONDONTWRITEBYTECODE=1

export PYTHONPATH="/seek/role-normalization:$PYTHONPATH"

echo "Running tests"

cd /seek/role-normalization/role_normalization/api

pytest --verbose --capture=tee-sys .
