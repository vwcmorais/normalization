#!/bin/bash

INTERVAL=$1
shift;

COMMAND="$@"

function _log {
    echo "[$(date '+%Y/%m/%d %H:%M:%S')] $1: $(basename $0): $2" > /dev/stderr;
}

function info {
    _log "INFO" "$1";
}

function warning {
    _log "WARNING" "$1";
}

function _help {
    echo "Usage: $0 <INTERVAL> <COMMAND>"
    echo "Runs <COMMAND> at <INTERVAL> seconds intervals."
    echo "We just sleep between runs, taking command execution time into account."
}

if [ -z "${INTERVAL}" -o -z "${COMMAND}" ]; then
    _help;
    exit;
fi

info "Starting to run provided command every ${INTERVAL} seconds."
LAST="$(date '+%s')";
while true; do
    ${COMMAND};
    NOW="$(date '+%s')";
    ELAPSED=$(( NOW - LAST ));
    LEFT=$(( INTERVAL - ELAPSED ));
    if [ "${LEFT}" -ge "0" ]; then
        info "Command execution took ${ELAPSED} seconds. ${LEFT} seconds left to sleep before next run."
        sleep ${LEFT};
    else
        warning "Command execution took ${ELAPSED} seconds. No time left to sleep between runs !."
    fi
    LAST="$(date '+%s')";
done
