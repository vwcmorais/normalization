#!/usr/bin/env python
#
# python3 role_normalization/api/models/gazetteers/check_thesaurus.py \
#   -f role_normalization/api/models/gazetteers/ptbr/mapping_thesaurus.txt \
#   -a API_AUTH_BASE_64_CREDENTIALS
#

import argparse
import logging
import re
import requests


logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

LOCAL_API_URL = 'http://localhost:8192/v1/role_normalization/catho'
LOCAL_API_DEFAULT_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}


def parse_args() -> argparse.ArgumentParser:
    """
    Parse command line arguments and return them.
    """
    args_parser = argparse.ArgumentParser(description='Process file line by line')
    args_parser.add_argument(
        '-f',
        help='Input file',
        type=str,
        metavar='INPUT_FILE',
        required=True,
        dest='input_file')
    args_parser.add_argument(
        '-a',
        help='API authentication, base64 encoded',
        type=str,
        metavar='BASE64_AUTH',
        required=True,
        dest='auth')
    args_parser.add_argument(
        '-v',
        help='Verbose',
        action='store_true',
        dest='verbose')
    return args_parser.parse_args()


def read_file(file_path: str) -> list:
    """
    Read a file line by line and return a list of lines.
    """
    log_lines = []
    with open(file_path) as file:
        lines = file.readlines()
        for line in lines:
            log_lines.append(line.strip())
    return log_lines


def check_for_terms_that_will_be_replaced(lines: list) -> None:
    """
    Check if terms that will be replaced are present in the following lines.
    """
    for i, line in enumerate(lines):
        logger.debug(f'Checking line {i}: {line}')
        terms = line.strip().split(',')
        if len(terms) < 2:
            print(f'Invalid line: {line.strip()}')
            continue
        replaced_terms = list(set(terms[1:]))
        for j, subseq_line in enumerate(lines[i+1:]):
            for replaced_term in replaced_terms:
                if re.search(r"( |,|^){}( |,|$)".format(replaced_term), subseq_line):
                    logger.warning(f'Term {replaced_term} present in lines {i+1} and {i+1 + j+1}')
                    logger.warning(f'Line {i+1}: {line}')
                    logger.warning(f'Line {i+1 + j+1}: {subseq_line}')


def check_for_distinct_roles_in_same_line(line: str, auth: str) -> None:
    """
    Check if role titles listed in a given line normalize to distinct database roles.
    """
    roles = []
    normalized_role_ids = []
    normalized_role_titles = []
    for role in line.split(','):
        logger.debug(f'Processing role: {role}')
        norm_result = normalize_role(role, auth)
        if norm_result:
            logger.debug(f'Role "{role}" normalized: {norm_result}')
            norm_role_id = norm_result['role_id']
            norm_role_title = norm_result['normalized_role']
            if norm_role_id not in normalized_role_ids:
                roles.append(role)
                normalized_role_ids.append(norm_role_id)
                normalized_role_titles.append(norm_role_title)
    if len(normalized_role_ids) > 1:
        logger.warning(f'Multiple normalized roles found in line: {line}')
        logger.warning(f'Normalized roles: {normalized_role_ids} / {roles} / {normalized_role_titles}')


def normalize_role(role: str, auth: str) -> str:
    """
    Normalize role via local API.
    """

    logger.debug(f'Normalizing role: {role}')

    norm_result = None

    try:
        api_headers = LOCAL_API_DEFAULT_HEADERS
        api_headers['Authorization'] = f'Basic {auth}'

        api_data = {'titles': [role]}

        api_response = requests.post(
            LOCAL_API_URL,
            headers=api_headers,
            json=api_data
        )

        logger.debug(f'Local API request data: {api_data}')
        logger.debug(f'Local API response: {api_response.status_code} / {api_response.text}')

        if api_response.status_code == 200:
            # Get first normalized role, if any
            api_response_data = api_response.json().get(role, {})
            norm_result = api_response_data[0] if len(api_response_data) else {}
    except Exception as ex:
        logger.exception(f'Error replaying request in local API: {str(ex)}')

    return norm_result


def main():
    # Get command line arguments
    args = parse_args()

    # Set log level
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger.setLevel(log_level)

    # Read file
    lines = read_file(args.input_file)
    logger.info(f'Read {len(lines)} lines from file {args.input_file}')

    # Process whole file
    check_for_terms_that_will_be_replaced(lines)
    logger.info(f'Checked {len(lines)} lines for terms that will be replaced')

    # Process lines
    for i, line in enumerate(lines):
        logger.debug(f'Processing line {i}: {line}')
        check_for_distinct_roles_in_same_line(line, args.auth)
    logger.info(f'Checked {len(lines)} lines for multiple roles')


if __name__ == '__main__':
    main()
