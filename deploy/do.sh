#!/bin/bash

export AWS_DEFAULT_REGION='us-east-1';
TERRAFORM_CMD='terraform_1.0'

COMMAND="$1"
WORKSPACE="$2"
SERVICE="$3"
shift
shift

function help()
{
    echo "Usage:"
    echo "  $0 <COMMAND> <WORKSPACE> <SERVICE> [SERVICE SERVICE ...]"
    echo
    echo "  <COMMAND>          Terraform commands: plan, apply, destroy, new, delete"
    echo "  <WORKSPACE>        See dir 'environments', ex: prod, staging..."
    echo "  <SERVICE>          See dir 'services', ex: api, worker, daemon..."
}


if [ -z "${COMMAND}" ] | [ -z "${WORKSPACE}" ] | [ -z "${SERVICE}" ]; then
    help;
    exit 1;
fi

BASEDIR="`dirname $0`";
cd ${BASEDIR};
WORKDIR="`pwd`";

KEEP='';

while [ -n "${SERVICE}" ]; do

    if ! [ -d "${WORKDIR}/services/${SERVICE}" ]; then
        echo "\"${SERVICE}\" is not a valid service name to deploy";
        echo "Valid service names are:";
        ls -1 ${WORKDIR}/services | grep -v variables.tf
        exit 1;
    fi

    echo
    echo "=====================================================================";
    echo "| Command: ${COMMAND}"
    echo "| Workspace: ${WORKSPACE}"
    echo "| Service: ${SERVICE}"
    echo "=====================================================================";
    echo

    cd "${WORKDIR}/services/${SERVICE}";
    if [ -d '.terraform' ]; then
        if [ -z "${KEEP}" ]; then
            echo -n "Keep terraform local state/plugins dir (.terraform) ? [Y/n]:"
            read ANS
        fi
        if [ "$( echo ${ANS} | tr '[A-Z]' '[a-z]' )" == "n" ]; then
            KEEP="N";
        else
            KEEP="Y";
        fi
        if [ "${KEEP}" == 'N' ]; then
	        rm -rf .terraform
        fi
    fi
    if ! [ -d '.terraform' ]; then
	    ${TERRAFORM_CMD} init;
    fi

    case ${COMMAND} in
        'apply'|'plan'|'destroy')
            ${TERRAFORM_CMD} workspace 'select' ${WORKSPACE} || exit 1;
            ${TERRAFORM_CMD} ${COMMAND} -var-file ../../environments/${WORKSPACE}/terraform.tfvars
            ;;
        'new'|'delete')
            ${TERRAFORM_CMD} workspace ${COMMAND} ${WORKSPACE};
            ;;
        *)
            echo "Unknown command/call method ($0).";
            help;
            exit 1;
    esac

    cd "${WORKDIR}";

    shift;
    SERVICE="$1"
done

