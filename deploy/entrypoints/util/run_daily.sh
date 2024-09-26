#!/bin/bash

TIME=$1
shift;

COMMAND="$@"

function _log {
    echo "[$(date '+%Y/%m/%d %H:%M:%S')] $1: $(basename $0): $2" > /dev/stderr;
}

function debug {
    if [ -n "${DEBUG}" ]; then
        _log "DEBUG" "$1";
    fi
}

function info {
    _log "INFO" "$1";
}

function warning {
    _log "WARNING" "$1";
}

function _help {
    echo "Usage: $0 <HH:MM>[:SS] <COMMAND>"
    echo "Runs <COMMAND> everyday at HH:MM"
    echo "Seconds are optional. Precision too, we just sleep between runs."
}

if [ -z "${TIME}" -o -z "${COMMAND}" ]; then
    _help;
    exit;
fi

info "Starting to run provided command daily at ${TIME} ($(date '+%Z'))"

NOW=$(date '+%s');
NEXT=$(date -d "tomorrow ${TIME}" '+%s');
LEFT=$(( NEXT - NOW ));
if [ "${LEFT}" -gt "86400" ]; then
    NEXT=$(date -d "today ${TIME}" '+%s');
    LEFT=$(( NEXT - NOW  ));
fi
sleep ${LEFT};

while true; do
    BEFORE="$(date '+%s')";
    ${COMMAND};
    AFTER="$(date '+%s')";
    ELAPSED=$(( AFTER - BEFORE ));
    NEXT=$(date -d "tomorrow ${TIME}" '+%s');
    NOW="$(date '+%s')";
    LEFT=$(( NEXT - NOW ));
    if [ "${ELAPSED}" -gt "86400" ]; then
        warning "Command execution took MORE THAN A DAY ! No time left to sleep between runs !"
    else
        info "Command execution took ${ELAPSED} seconds. Sleeping for ${LEFT} seconds until next run."
        sleep ${LEFT};
    fi
done
