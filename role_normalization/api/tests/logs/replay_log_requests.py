#!/usr/bin/env python

import argparse
import csv
import datetime
import json
import logging
import random
import requests
import sys
import time
from collections import OrderedDict
from tqdm import tqdm
from typing import Tuple


"""
Run:
python3 role_normalization/api/tests/logs/replay_log_requests.py \
    -l LOG_FILE \
    -a API_AUTH
"""


log_file = f'replay_log_requests-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}.log'
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

LOCAL_API_URL_PREFIX = 'http://localhost:8192'
LOCAL_API_DEFAULT_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}


def parse_args():
    """
    Parse command line arguments and return them.
    """
    args_parser = argparse.ArgumentParser(description='Read a Role Normalization API log file, make the same requests to an API running locally and compare the responses.')
    args_parser.add_argument(
        '-l',
        help='Role Normalization API logs file - extracted from Loglake, for example',
        type=str,
        metavar='LOG_FILE',
        required=True,
        dest='log_file')
    args_parser.add_argument(
        '-a',
        help='Role Normalization API authentication, base64 encoded',
        type=str,
        metavar='BASE64_AUTH',
        required=True,
        dest='auth')
    args_parser.add_argument(
        '-n',
        help='Limit number of requests replicated',
        type=int,
        metavar='NUM_REQUESTS',
        dest='limit')
    args_parser.add_argument(
        '-s',
        help='Random seed',
        type=int,
        metavar='RANDOM_SEED',
        dest='seed')
    args_parser.add_argument(
        '-w',
        help='Write non-normalized role titles to file',
        action='store_true',
        dest='write_non_norm_titles')
    args_parser.add_argument(
        '-v',
        help='Verbose',
        action='store_true',
        dest='verbose')
    return args_parser.parse_args()


def read_log_file(log_file: str) -> list:
    """
    Read CSV log file generated from Loglake API logs. Expected CSV format:
        log_datetime,api_uri,api_request,api_response
        ROW_LOG_DATETIME,ROW_API_URI,ROW_API_REQUEST,ROW_API_RESPONSE
        ...
    Returns a list containing tuples with 3 strings:
    - Request URI: '/v1/role_normalization/catho' or '/v1/role_normalization/catho?perfil_ids=PERFIL_IDS'
    - Request JSON: '{"titles": ["ROLE_TITLE"]}'
    - Response JSON: '{"ROLE_TITLE": [{"normalized_role": "NORM_ROLE_TITLE", "role_id": NORM_ROLE_ID, "seniority": ["SENIORITY"], "hierarchy": ["HIERARCHY"]}, ...]}'
    """
    log_lines = []
    try:
        with open(log_file) as csv_file:
            csv_reader = csv.DictReader(csv_file, delimiter=',')
            csv.field_size_limit(sys.maxsize)
            rows_count = 0
            invalid_lines_count = 0
            for row in csv_reader:
                # Skip first row - CSV header
                if rows_count == 0:
                    rows_count += 1
                    continue
                if not row or not row['api_uri'] or not row['api_request']:
                    logger.debug(f'Invalid log line ({rows_count+1}): {row}')
                    invalid_lines_count += 1
                    continue
                log_lines.append((row['api_uri'], row['api_request'], row['api_response'] or '{}'))
                rows_count += 1
            logger.warning(f'Invalid log lines, skipped: {invalid_lines_count}')
    except Exception as e:
        logger.exception(f'Error reading log file (around line {rows_count}): {log_file}')
        raise e
    return log_lines


def process_log_lines(log_lines: list, write_non_norm_titles: bool = False) -> list:
    """
    Receive a list of log lines and return requests and expected responses. Returned
    tuples will contain the request URI, the received role title and, if available,
    the first normalized role title and the corresponding role ID.
    Tuple examples:
        ('/v1/role_normalization/catho', 'Qualquer cargo', None, None)
        ('/v1/role_normalization/catho?perfil_ids=3', 'Tec enfermagem', 'Técnico em Enfermagem', 1474)
        ('/v1/role_normalization/catho', 'Vendedor, Balconista', 'Vendedor', 1164)
    """

    requests_responses = []
    non_norm_titles = []
    invalid_req_resp_count = 0

    for i, req_data in enumerate(log_lines):
        logger.debug(f'Processing log line {i}/{len(log_lines)}: {log_lines[i]}')

        uri, req, resp = req_data
        req_json = json.loads(req)
        resp_json = json.loads(resp)
        logger.debug(f'Request JSON: {req_json}')
        logger.debug(f'Response JSON: {resp_json}')

        received_titles = req_json.get('titles', [])
        # Invalid request - no "titles" key in request JSON
        if not received_titles:
            invalid_req_resp_count += 1
            logger.debug(f'Invalid URI/request/response: {uri} / {req} / {resp}')
            continue
        # For each received title in request's "titles" key
        for received_title in received_titles:

            # Received title could not be normalized
            # Empty response or title not found in response JSON
            if not resp_json or not resp_json.get(received_title, []):

                if write_non_norm_titles:
                    non_norm_titles.append(received_title)

                # Add request with no response to the list
                proc_req_resp = (uri, received_title, None, None)
                logger.debug(f'Adding URI/request/response: {proc_req_resp}')
                requests_responses.append(proc_req_resp)
                continue

            # Received title could be normalized
            # Title found in response JSON
            norm_result = resp_json.get(received_title, [])
            first_norm_role = norm_result[0] if len(norm_result) else {}
            norm_title = first_norm_role.get('normalized_role')
            norm_role_id = first_norm_role.get('role_id')

            # Invalid response - no normalized_role or role_id in response JSON
            if not norm_title or not norm_role_id:
                invalid_req_resp_count += 1
                logger.debug(f'Invalid URI/request/response: {uri} / {req} / {resp}')
                continue

            # Add request and normalized role to the list
            proc_req_resp = (uri, received_title, norm_title, int(norm_role_id))
            logger.debug(f'Adding URI/request/response: {proc_req_resp}')
            requests_responses.append(proc_req_resp)

    if invalid_req_resp_count:
        logger.warning(f'Invalid requests, skipped: {invalid_req_resp_count}')

    # Write non-normalized role titles to file
    if write_non_norm_titles:
        non_norm_titles = sorted(non_norm_titles)
        with open('non_norm_titles.txt', 'w') as non_norm_titles_file:
            for non_norm_title in non_norm_titles:
                non_norm_titles_file.write(f'{non_norm_title}\n')
        logger.info(f'{len(non_norm_titles)} non-normalized titles written to non_norm_titles.txt')

    return requests_responses


def replay_requests(requests_responses: list, auth: str) -> Tuple[dict, dict, dict, dict, dict]:
    """
    Receive a list of requests and expected responses, replay them to the local API and
    compare the responses.
    """

    # Cases to be considered when comparing role IDs:
    #
    #              Possible role IDs
    # Remote API   None    123     123      123          None
    # Local API    None    123     456      None         123
    # Result       Match   Match   Differ   Regression   Improvement

    match_none = OrderedDict()
    match_norm = OrderedDict()
    differ = OrderedDict()
    regressions = OrderedDict()
    improvements = OrderedDict()

    api_headers = LOCAL_API_DEFAULT_HEADERS
    api_headers['Authorization'] = f'{auth}' if auth.startswith('Basic ') else f'Basic {auth}'

    for request_response in tqdm(requests_responses):

        uri, received_title, normalized_title, role_id = request_response
        logger.debug(f'Replaying request: {request_response}')

        local_api_normalized_title = None
        local_api_role_id = None

        try:

            api_data = {'titles': [received_title]}

            api_response = requests.post(
                LOCAL_API_URL_PREFIX + uri,
                headers=api_headers,
                json=api_data
            )

            logger.debug(f'Local API request data: {api_data}')
            logger.debug(f'Local API response: {api_response.status_code} / {api_response.text}')

            if api_response.status_code == 200:
                # Get first normalized role title, if any
                api_response_data = api_response.json().get(received_title, [])
                api_response_data = api_response_data[0] if len(api_response_data) else {}
                local_api_normalized_title = api_response_data.get('normalized_role')
                local_api_role_id = api_response_data.get('role_id')
                local_api_role_id = int(local_api_role_id) if local_api_role_id else None
            elif api_response.status_code >= 400:
                logger.warning(f'Local API request failed: {api_response.status_code} / {api_response.text}')
        except Exception as ex:
            logger.exception(f'Error replaying request in local API: {str(ex)}')

        remote_result = f'{role_id or "-"}: {normalized_title or "-"}' if role_id else '-'
        local_result = f'{local_api_role_id or "-"}: {local_api_normalized_title or "-"}' if local_api_role_id else '-'
        responses_comparison = {
            'Remote': remote_result,
            'Local': local_result
        }

        # Couldn't be normalized in both APIs
        if not role_id and not local_api_role_id:
            match_none[received_title] = responses_comparison
        # Could be normalized in both APIs and responses match
        elif role_id and local_api_role_id and role_id == local_api_role_id:
            match_norm[received_title] = responses_comparison
        # Could be normalized in both APIs but responses don't match
        elif role_id and local_api_role_id and role_id != local_api_role_id:
            differ[received_title] = responses_comparison
        # Could be normalized in remote API but not in local API
        elif role_id and not local_api_role_id:
            regressions[received_title] = responses_comparison
        # Couldn't be normalized in remote API but could be in local API
        elif not role_id and local_api_role_id:
            improvements[received_title] = responses_comparison

    return match_none, match_norm, differ, regressions, improvements


def print_results(match_none: dict, match_norm: dict, differ: dict, regressions: dict, improvements: dict, elapsed_time: float) -> None:
    total_requests = len(match_none) + len(match_norm) + len(differ) + len(regressions) + len(improvements)
    logger.info('Results:')
    logger.info(f'Non-normalized matches ({len(match_none)}, {len(match_none)/total_requests:.2%}): {json.dumps(match_none, indent=4, ensure_ascii=False)}')
    logger.info(f'Normalized matches ({len(match_norm)}, {len(match_norm)/total_requests:.2%}): {json.dumps(match_norm, indent=4, ensure_ascii=False)}')
    logger.info(f'Differences ({len(differ)}, {len(differ)/total_requests:.2%}): {json.dumps(differ, indent=4, ensure_ascii=False)}')
    logger.info(f'Regressions ({len(regressions)}, {len(regressions)/total_requests:.2%}): {json.dumps(regressions, indent=4, ensure_ascii=False)}')
    logger.info(f'Improvements ({len(improvements)}, {len(improvements)/total_requests:.2%}): {json.dumps(improvements, indent=4, ensure_ascii=False)}')
    logger.info(f'{len(match_none)} ({len(match_none)/total_requests:.2%}) requests matched - not normalized')
    logger.info(f'{len(match_norm)} ({len(match_norm)/total_requests:.2%}) requests matched - normalized to same role ID')
    logger.info(f'{len(differ)} ({len(differ)/total_requests:.2%}) requests differed - normalized to distinct role IDs')
    logger.info(f'{len(regressions)} ({len(regressions)/total_requests:.2%}) requests were regressions - could be normalized before but can\'t be normalized now')
    logger.info(f'{len(improvements)} ({len(improvements)/total_requests:.2%}) requests were improvements - couldn\'t be normalized before but can be normalized now')
    logger.info(f'Requests replayed in {elapsed_time:.2f} seconds')


def main():
    # Get command line arguments
    args = parse_args()

    # Set log level
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger.setLevel(log_level)

    # Print command line arguments
    logger.info(f'Command line arguments: {args}')

    # Read Role Normalization API log file
    log_lines = read_log_file(args.log_file)
    logger.info(f'Read {len(log_lines)} lines from {args.log_file}')
    for i, line in enumerate(log_lines):
        logger.debug(f'Line {i}: {line}')

    # Process log lines and get requests and expected responses
    requests_responses = process_log_lines(log_lines, write_non_norm_titles=args.write_non_norm_titles)
    logger.info(f'Got {len(requests_responses)} requests and expected responses')
    for i, request_response in enumerate(requests_responses):
        logger.debug(f'Request {i}: {request_response}')

    # Limit number of requests
    if args.limit and args.limit < len(requests_responses):
        random.Random(args.seed).shuffle(requests_responses)
        requests_responses = requests_responses[:args.limit]
        logger.info(f'Requests limited to {len(requests_responses)} using random seed {args.seed}')

    # Replay requests using the local API
    logger.info(f'Replaying requests to local API...')
    start_time = time.time()
    match_none, match_norm, differ, regressions, improvements = replay_requests(requests_responses, args.auth)
    elapsed_time = time.time() - start_time
    logger.info(f'Replayed requests to local API in {elapsed_time:.2f} seconds')

    # Print results
    print_results(match_none, match_norm, differ, regressions, improvements, elapsed_time)

    logger.info(f'Log saved to file: {log_file}')


if __name__ == '__main__':
    main()
