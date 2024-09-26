#!/bin/bash
#
# See Development Environment in README.md
#

API_DIR="$( cd -- "$(dirname "$0")" > /dev/null 2>&1; pwd -P )"
MODULE_DIR="$( dirname "$API_DIR" )"
REPO_DIR="$( dirname "$MODULE_DIR" )"

export PYTHONPATH="$REPO_DIR:$PYTHONPATH"
export LOG_LEVEL=${LOG_LEVEL:="DEBUG"}
echo "DEBUG: PYTHONPATH = $PYTHONPATH"

cd "$API_DIR"
gunicorn --reload --log-level debug --workers 1 --config ./gunicorn_conf.py api:app
