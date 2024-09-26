import click
import json
import pika
import pymysql
import requests
import time
import traceback
from datetime import datetime, timezone
from tenacity import retry, stop_after_attempt, wait_fixed
from typing import List, Tuple

from role_normalization import settings



"""
Role Normalization routine:
For roles in Catho active user's CVs and past work experiences, find the corresponding role ID
using the Role Normalization API and save it in Catho's databases.
"""



# Represents a role that's associated with a specific user and CV
# Additionally it can also be associated with a work experience
class Role:

    def __init__(self, user_id, cv_id, role, role_id=None, work_exp_id=None):
        self.user_id = user_id
        self.cv_id = cv_id
        self.role = role
        self.role_id = role_id
        self.work_exp_id = work_exp_id

    def __repr__(self):
        return f'Role(user_id={self.user_id}, cv_id={self.cv_id}, work_exp_id={self.work_exp_id}, role={self.role}, role_id={self.role_id})'



# Class to publish messages to a RabbitMQ queue
class RabbitMQPublisher:

    # Reusable connection and channel
    connection = None
    channel = None

    def __init__(self, queue_name, host=None, port=None, username=None, password=None):

        # Check parameters
        if not queue_name or not host or not port or not username or not password:
            raise ValueError('RabbitMQPublisher: __init__(): missing required parameters')

        # If not yet connected, connect
        if not self.connection:
            _log('RabbitMQ: connecting...', 'debug')
            self.connect(host, port, username, password)
        # If connection died, reconnect
        try:
            self.connection.process_data_events()
        except:
            _log('RabbitMQ: connection lost - reconnecting...', 'warning')
            self.connect(host, port, username, password)

        # Declare queue
        self.queue_name = queue_name
        self.channel.queue_declare(queue=self.queue_name, durable=True)

    @classmethod
    def connect(cls, host=None, port=None, username=None, password=None):

        # Check parameters
        if not host or not port or not username or not password:
            raise ValueError('RabbitMQPublisher: connect(): missing required parameters')

        credentials = pika.PlainCredentials(username, password)
        parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            credentials=credentials,
            socket_timeout=300,
            heartbeat=600)
        cls.connection = pika.BlockingConnection(parameters)
        cls.channel = cls.connection.channel()
        cls.channel.confirm_delivery()
        cls.channel.basic_qos(prefetch_count=1)
        _log('RabbitMQ: connection established', 'debug')

    @classmethod
    def disconnect(cls):
        if not cls.connection or cls.connection.is_closed:
            _log('RabbitMQ: connection not established or already closed', 'warning')
            return
        cls.channel.close()
        cls.channel = None
        cls.connection.close()
        cls.connection = None
        _log('RabbitMQ: connection closed', 'debug')

    def publish_msg(self, msg):
        persist_msg_code = 2
        body = json.dumps(msg)
        properties = pika.BasicProperties(delivery_mode=persist_msg_code)
        _log(f'RabbitMQ: publishing message: {body}', 'debug')
        self.channel.basic_publish(
            exchange='',
            routing_key=self.queue_name,
            body=body,
            properties=properties
        )
        _log('RabbitMQ: message published', 'debug')



def _log(log_message: str, log_level: str):
    """
    Print log message in JSON format.

    :param str log_message: Message to log
    :param str log_level: Message log level
    """

    # If message is empty, log and return
    if not log_message.strip():
        _log(f'Empty log message: log_message = "{str(log_message)}", log_level = "{str(log_level)}"', 'error')
        return

    log_level = log_level.upper()

    # If log level is not one of the above, log and return
    if log_level not in settings.valid_log_levels:
        _log(f'Invalid log level: log_message = "{str(log_message)}", log_level = "{str(log_level)}"', 'error')
        return

    # If message log level is of lower priority than _LOG_LEVEL, return
    if settings.valid_log_levels.index(log_level) > settings.valid_log_levels.index(_LOG_LEVEL):
        return

    json_log_message = {}
    json_log_message['@timestamp'] = str(datetime.now(timezone.utc).isoformat()[:-9] + 'Z')
    json_log_message['@version'] = '1'
    json_log_message['appname'] = 'catho-role-normalization-routine'
    json_log_message['log_level'] = str(log_level)
    json_log_message['message'] = str(log_message)

    print(json.dumps(json_log_message))



#
# Enable/Disable flags, to be used during development
# If disabled, queries and queue messages are just printed, not executed/enqueued
#

WRITE_NORM_ROLE = True
WRITE_FLAG = True
ENQUEUE_IDS = True

#
# Logging settings
#

_LOG_LEVEL = settings.routine_log_level
if _LOG_LEVEL not in settings.valid_log_levels:
    _LOG_LEVEL = 'INFO'
_log('Populating local variables with values from AWS Secrets Manager', 'info')
_log(f'Environment set to {settings.env}', 'info')
_log(f'Log level set to {_LOG_LEVEL}', 'info')

#
# MySQL settings
#

# Query to retrieve non-normalized CV roles
_DB_GET_CV_ROLES_QUERY = """
    SELECT
        DISTINCT
        u.usr_id AS user_id,
        c.cur_id AS cv_id,
        c.objetivo AS cv_role
    FROM
        conline.usr AS u
        INNER JOIN conline.cur AS c ON u.usr_id = c.usr_id
        LEFT JOIN conline.cur_cargo AS cca ON c.cur_id = cca.cur_id
    WHERE
        u.status = 'A' -- only active users
        AND u.organizacao_id = 1 -- only Catho users
        AND c.objetivo IS NOT NULL AND c.objetivo != '' -- only CVs with a non-null role text field
        AND (
            cca.cargo_id IS NULL -- CVs with a null role ID field
            OR cca.cargo_id = 0 -- or CVs with an invalid role ID field
        )
        {date_filter}
    {limit_clause}
    ;
"""

# Query to retrieve non-normalized work experience roles
_DB_GET_WORK_EXPERIENCE_ROLES_QUERY = """
    SELECT
        DISTINCT
        u.usr_id AS user_id,
        c.cur_id AS cv_id,
        cep.curexpprof_id AS cv_work_exp_id,
        cep.cargo AS cv_work_exp_role
    FROM
        conline.usr AS u
        INNER JOIN conline.cur AS c ON u.usr_id = c.usr_id
        INNER JOIN conline.curexpprof AS cep ON c.cur_id = cep.cur_id
        LEFT JOIN conline.curexpprof_adicionais AS cepa ON cep.curexpprof_id = cepa.curexpprof_id
    WHERE
        u.status = 'A' -- only active users
        AND u.organizacao_id = 1 -- only Catho users
        AND cep.cargo IS NOT NULL AND cep.cargo != '' -- only CVs with a non-null work experience role text field
        AND (
            cepa.cargo_id IS NULL -- CVs with a null work experience role ID field
            OR cepa.cargo_id = 0 -- or CVs with an invalid work experience role ID field
        )
        {date_filter}
    {limit_clause}
    ;
"""

# CV role table
_DB_CV_WRITE_TABLE = settings.mysql_cv_write_table()

# Query to insert CVs that are not present in the CV roles table
_DB_INSERT_CV_ROLE_QUERY = """
    INSERT INTO
        {cv_role_table} (cur_id, cargo_id)
    SELECT
        d.cur_id, d.cargo_id
    FROM
        (
            {select_with_values}
        ) AS d
    WHERE
        NOT EXISTS (
            SELECT 1
            FROM {cv_role_table} AS t
            WHERE t.cur_id = d.cur_id
        )
    ;
"""

# Query to update CV roles in the CV roles table
_DB_UPDATE_CV_ROLE_QUERY = """
    UPDATE IGNORE
        {cv_role_table}
    SET
        cargo_id = (
            CASE cur_id
                {case_conditions}
            END
        )
    WHERE
        cur_id IN ({cv_ids})
    ;
"""

# Work experience role tables
_DB_WORK_EXP_PARENT_TABLE = settings.mysql_work_exp_parent_table()
_DB_WORK_EXP_WRITE_TABLE = settings.mysql_work_exp_write_table()

# Query to insert work experiences that are not present in the work experience roles table
_DB_INSERT_WORK_EXPERIENCE_ROLE_QUERY = """
    INSERT INTO
        {work_exp_role_table} (curexpprof_id, cargo_id)
    SELECT
        d.curexpprof_id, d.cargo_id
    FROM
        (
            {select_with_values}
        ) AS d
    WHERE
        EXISTS (
            SELECT 1
            FROM {work_exp_parent_table} AS t
            WHERE t.curexpprof_id = d.curexpprof_id
        )
        AND NOT EXISTS (
            SELECT 1
            FROM {work_exp_role_table} AS t
            WHERE t.curexpprof_id = d.curexpprof_id
        )
    ;
"""

# Query to update work experience roles in the work experience roles table
_DB_UPDATE_WORK_EXPERIENCE_ROLE_QUERY = """
    UPDATE IGNORE
        {work_exp_role_table}
    SET
        cargo_id = (
            CASE curexpprof_id
                {case_conditions}
            END
        )
    WHERE
        curexpprof_id IN ({work_exp_ids})
    ;
"""

_DB_FLAG_WRITE_TABLE = settings.mysql_flag_write_table()

# Query to insert/update flag indicating that a role was normalized by this routine
_DB_UPSERT_FLAG_QUERY = """
    INSERT INTO
        {role_flag_table} (usr_id, cur_id, curexpprof_id, cargo_id)
    VALUES
        {flag_values}
    ON DUPLICATE KEY UPDATE
        cargo_id = VALUES(cargo_id)
    ;
"""

# MySQL read connection and cursor, shared between methods
_DB_READ_CONNECTION = None
_DB_READ_CURSOR = None

# MySQL connection settings
_DB_USER = settings.mysql_user()
_DB_PASSWORD = settings.mysql_passwd()
_DB_READ_HOST = settings.mysql_read_host()
_DB_READ_LIMIT_CLAUSE = settings.mysql_read_limit_clause()
_DB_WRITE_HOST = settings.mysql_write_host()
_DB_FLAG_WRITE_HOST = settings.mysql_flag_write_host()

# MySQL date filter
# Week by week for the past 24 weeks (6 months)
_DB_DATE_FILTER_STEPS = []
_DB_DATE_FILTER_STEPS_PRETTY_NAME = []
for week in range(0,24,1):
    _DB_DATE_FILTER_STEPS.append(
        f"AND c.data_alteracao BETWEEN SUBDATE( NOW(), INTERVAL {week + 1} WEEK ) AND SUBDATE( NOW(), INTERVAL {week} WEEK )"
    )
    _DB_DATE_FILTER_STEPS_PRETTY_NAME.append(f'{week + 1} week(s) ago')
# Days left between week and month intervals
_DB_DATE_FILTER_STEPS.append(
    "AND c.data_alteracao BETWEEN SUBDATE( NOW(), INTERVAL 6 MONTH ) AND SUBDATE( NOW(), INTERVAL 24 WEEK )"
)
_DB_DATE_FILTER_STEPS_PRETTY_NAME.append(f'24 weeks ago - leftover days between week and month intervals')
# Month by month from 6 months ago to 12 months ago (1 year)
for month in range(6,12,1):
    _DB_DATE_FILTER_STEPS.append(
        f"AND c.data_alteracao BETWEEN SUBDATE( NOW(), INTERVAL {month + 1} MONTH ) AND SUBDATE( NOW(), INTERVAL {month} MONTH )"
    )
    _DB_DATE_FILTER_STEPS_PRETTY_NAME.append(f'{month + 1} month(s) ago')
_DB_CURRENT_DATE_FILTER_INDEX = 0
_DB_RERUN_READ_QUERY = True
_DB_DATE_FILTERING_DONE = False
# Sleep between date ranges to avoid overloading the Role Normalization API
# Also helps to keep CPU usage low
_SLEEP_SECS_BETWEEEN_DATE_RANGES = 30

_log(f'MySQL read host: {_DB_READ_HOST}', 'info')
if _DB_READ_LIMIT_CLAUSE:
    _log(f'MySQL read limit clause: {_DB_READ_LIMIT_CLAUSE}', 'info')
_log(f'MySQL write host: {_DB_WRITE_HOST}', 'info')
_log(f'MySQL CV write table: {_DB_CV_WRITE_TABLE}', 'info')
_log(f'MySQL work experience write table: {_DB_WORK_EXP_WRITE_TABLE}', 'info')
_log(f'MySQL log write host: {_DB_FLAG_WRITE_HOST}', 'info')
_log(f'MySQL log write table: {_DB_FLAG_WRITE_TABLE}', 'info')

#
# AB test settings
#

# Flag that indicates if an AB test is being run
_AB_TEST_ENABLED = settings.ab_test_enabled

# If an AB test is being run, normalize roles only for users in this group
_AB_TEST_GROUP = settings.ab_test_group

# AB test API settings
_AB_TEST_API_NAME = settings.ab_test_api_name()
_AB_TEST_API_HOST = settings.ab_test_api_host()
_AB_TEST_API_AUTH = settings.ab_test_api_auth()

if _AB_TEST_ENABLED:
    _log(f'AB test enabled', 'info')
    _log(f'AB test API host: {_AB_TEST_API_HOST}', 'info')
    _log(f'AB test name: {_AB_TEST_API_NAME}', 'info')
    _log(f'AB test variant group: {_AB_TEST_GROUP}', 'info')

#
# Role Normalization API settings
#

_ROLE_NORM_API_HOST = settings.role_norm_api_host()
_ROLE_NORM_API_AUTH = settings.role_norm_api_auth()

_log(f'Role Normalization API host: {_ROLE_NORM_API_HOST}', 'info')

#
# RabbitMQ settings
#
_RABBITMQ_HOST = settings.rabbitmq_host()
_RABBITMQ_PORT = settings.rabbitmq_port()
_RABBITMQ_USERNAME = settings.rabbitmq_username()
_RABBITMQ_PASSWORD = settings.rabbitmq_password()
_RABBITMQ_INDEX_USERS_ES_QUEUE = settings.rabbitmq_index_users_es_queue

_log(f'RabbitMQ host: {_RABBITMQ_HOST}:{_RABBITMQ_PORT}', 'info')



@click.command()
@click.option('-nt', '--norm-type', required=True, type=click.Choice(['cv', 'work_exp'], case_sensitive=False),
                help='Type of normalization to run, either "cv" for CV roles or "work_exp" for work experience roles')
@click.option('-drs', '--db-read-batch-size', default=5000, show_default=True, help='Read this many entries from database at a time')
@click.option('-abs', '--api-batch-size', default=1000, show_default=True, help='Send this many entries to Role Normalization API at a time')
@click.option('-dws', '--db-write-batch-size', default=250, show_default=True, help='Write this many entries to database at a time')
@click.option('-qbs', '--queue-batch-size', default=100, show_default=True, help='Enqueue this many entries to RabbitMQ at a time')
def main(norm_type: str, db_read_batch_size: int, api_batch_size: int, db_write_batch_size: int, queue_batch_size: int) -> None:
    """
    Normalize CV and work experience roles found in Catho's database. A non-normalized
    role is sent to the Role Normalization API that returns the corresponding role ID
    used by Catho for this role. The role ID is then written in the CV or work experience
    entry in Catho's database and flagged as updated by this routine.
    """
    _log(f'Parameter db_read_batch_size = {db_read_batch_size}', 'debug')
    _log(f'Parameter api_batch_size = {api_batch_size}', 'debug')
    _log(f'Parameter db_write_batch_size = {db_write_batch_size}', 'debug')
    _log(f'Parameter queue_batch_size = {queue_batch_size}', 'debug')
    _role_normalization(norm_type, db_read_batch_size, api_batch_size, db_write_batch_size, queue_batch_size)



def _role_normalization(norm_type: str, db_read_batch_size: int, api_batch_size: int, db_write_batch_size: int, queue_batch_size: int) -> None:

    if _AB_TEST_ENABLED:
        _log(f'AB test being run, normalizing roles only of CVs and work experiences belonging to group "{_AB_TEST_GROUP}"', 'warning')

    if norm_type == 'cv':
        _log('Normalize CV roles', 'info')
        to_normalize_count, normalized_count, written_count, total_non_normalized_count = _normalize_roles('cv_role', db_read_batch_size, api_batch_size, db_write_batch_size, queue_batch_size)
        _log(f'Normalized CV roles: {normalized_count} / {to_normalize_count} (Total non-normalized: {total_non_normalized_count})', 'info')
        if normalized_count != written_count:
            _log(f'Difference between CV roles normalized and written to database: {written_count} / {normalized_count}', 'warning')

    elif norm_type == 'work_exp':
        _log('Normalize work experience roles', 'info')
        to_normalize_count, normalized_count, written_count, total_non_normalized_count = _normalize_roles('work_exp_role', db_read_batch_size, api_batch_size, db_write_batch_size, queue_batch_size)
        _log(f'Normalized work experience roles: {normalized_count} / {to_normalize_count} (Total non-normalized: {total_non_normalized_count})', 'info')
        if normalized_count != written_count:
            _log(f'Difference between work experience roles normalized and written to database: {written_count} / {normalized_count}', 'warning')



def _normalize_roles(role_field: str, db_read_batch_size: int, api_batch_size: int, db_write_batch_size: int, queue_batch_size: int) -> Tuple[int, int, int, int]:
    """
    Command to normalize a specific role type, either CV roles or work experience roles.

    :param str role_field: Role type to normalize, either CV roles or work experience roles
    :param int db_read_batch_size: Read this many entries from database at a time
    :param int api_batch_size: Send this many entries to Role Normalization API at a time
    :param int db_write_batch_size: Write this many entries to database at a time
    :param int queue_batch_size: Enqueue this many entries into RabbitMQ at a time
    :return Tuple[int, int, int, int]: Count of roles to normalize that belong to a given AB test group, roles normalized, roles written to database and total non-normalized roles
    """

    if role_field not in ['cv_role', 'work_exp_role']:
        _log(f'Unknown role type: {role_field}', 'error')
        return (0, 0, 0)

    if not db_read_batch_size:
        _log('DB read batch size not set', 'error')
        return (0, 0, 0)

    if not api_batch_size:
        _log('API batch size not set', 'error')
        return (0, 0, 0)

    if not db_write_batch_size:
        _log('DB write batch size not set', 'error')
        return (0, 0, 0)

    global _DB_READ_CONNECTION
    global _DB_READ_CURSOR
    global _DB_DATE_FILTERING_DONE

    to_normalize_count = 0
    normalized_count = 0
    written_count = 0
    flag_written_count = 0
    total_non_normalized_count = 0
    roles_enqueued_count = 0

    if role_field == 'cv_role':
        role_type_in_logs = 'CV roles'
    elif role_field == 'work_exp_role':
        role_type_in_logs = 'work experience roles'

    try:

        while True:

            # Get batch of roles to normalize
            _log(f'Get batch of {role_type_in_logs} to normalize from database', 'info')
            roles_to_normalize = _get_roles_to_normalize(role_field, db_read_batch_size)
            _log(f'Got batch of {role_type_in_logs} to normalize from database: {len(roles_to_normalize)}', 'info')

            # Stop once all batches have been processed and date filtering is done
            if not roles_to_normalize:
                if _DB_DATE_FILTERING_DONE:
                    _log('Date filtering done', 'debug')
                    _log('Close read connection to database', 'debug')
                    if _DB_READ_CURSOR:
                        _DB_READ_CURSOR.close()
                        _DB_READ_CURSOR = None
                    if _DB_READ_CONNECTION:
                        _DB_READ_CONNECTION.close()
                        _DB_READ_CONNECTION = None
                    _log('Closed read connection to database', 'debug')
                    break
                else:
                    _log('Current date filtering done, moving to next one', 'debug')
                    continue

            roles_api_batch = []
            normalized_roles = []

            to_normalize_batch_count = 0
            normalized_batch_count = 0
            written_batch_count = 0
            flag_written_batch_count = 0
            total_non_normalized_batch_count = 0
            roles_enqueued_batch_count = 0

            # For each role to be normalized
            for role in roles_to_normalize:

                total_non_normalized_batch_count += 1

                # If there's an AB test being run, check if the current user is in the expected group
                if _AB_TEST_ENABLED:
                    if not _is_part_of_ab_test_group(role.user_id, _AB_TEST_GROUP):
                        continue

                to_normalize_batch_count += 1

                # Gather roles in batches to be sent to the Role Normalization API
                roles_api_batch.append(role)

                # Normalize batch of roles through the Role Normalization API
                if len(roles_api_batch) == api_batch_size:
                    _log(f'Normalize batch of {role_type_in_logs} via API: {len(roles_api_batch)}', 'info')
                    normalized_roles_batch = _get_normalized_roles(role_field, roles_api_batch)
                    normalized_roles.extend(normalized_roles_batch)
                    normalized_batch_count += len(normalized_roles_batch)
                    _log(f'Normalized batch of {role_type_in_logs} via API: {len(normalized_roles_batch)}', 'info')
                    roles_api_batch = []

            # Normalize the last batch of roles through the Role Normalization API
            if len(roles_api_batch) > 0:
                _log(f'Normalize batch of {role_type_in_logs} via API: {len(roles_api_batch)}', 'info')
                normalized_roles_batch = _get_normalized_roles(role_field, roles_api_batch)
                normalized_roles.extend(normalized_roles_batch)
                normalized_batch_count += len(normalized_roles_batch)
                _log(f'Normalized batch of {role_type_in_logs} via API: {len(normalized_roles_batch)}', 'info')

            # Write normalized roles to database, in batches
            _log(f'Write batch of normalized {role_type_in_logs} to database: {len(normalized_roles)}', 'info')
            roles_to_write = [normalized_roles[i : i+db_write_batch_size] for i in range(0, len(normalized_roles), db_write_batch_size)]
            for i, roles_to_write_batch in enumerate(roles_to_write):
                _log(f'Process batch of normalized {role_type_in_logs}: {i+1} / {len(roles_to_write)}', 'info')
                written_batch_count += _write_normalized_roles(role_field, roles_to_write_batch)
            _log(f'Wrote batch of normalized {role_type_in_logs} to database: {written_batch_count}', 'info')
            if written_batch_count != normalized_batch_count:
                _log(f'Not all normalized roles were updated in database: {written_batch_count} / {normalized_batch_count}', 'warning')

            # Write flag to database indicating roles were normalized, in batches
            _log(f'Write batch of flags indicating {role_type_in_logs} were written to database: {len(normalized_roles)}', 'info')
            flags_to_write = [normalized_roles[i : i+db_write_batch_size] for i in range(0, len(normalized_roles), db_write_batch_size)]
            for i, flags_to_write_batch in enumerate(flags_to_write):
                _log(f'Process batch of normalized {role_type_in_logs}: {i+1} / {len(flags_to_write)}', 'info')
                flag_written_batch_count += _write_normalized_role_flags(flags_to_write_batch)
            _log(f'Wrote batch of flags indicating {role_type_in_logs} were written to database: {flag_written_batch_count}', 'info')

            # Enqueue normalized IDs to be indexed by RecSys, in batches
            _log(f'Enqueue normalized {role_type_in_logs} into RabbitMQ: {len(normalized_roles)}', 'info')
            roles_to_enqueue = [normalized_roles[i : i+queue_batch_size] for i in range(0, len(normalized_roles), queue_batch_size)]
            for i, roles_to_enqueue_batch in enumerate(roles_to_enqueue):
                _log(f'Process batch of normalized {role_type_in_logs}: {i+1} / {len(roles_to_enqueue)}', 'info')
                roles_enqueued_batch_count += _enqueue_normalized_user_ids(role_field, roles_to_enqueue_batch)
            _log(f'Enqueued normalized {role_type_in_logs} into RabbitMQ: {roles_enqueued_batch_count}', 'info')

            to_normalize_count += to_normalize_batch_count
            normalized_count += normalized_batch_count
            written_count += written_batch_count
            flag_written_count += flag_written_batch_count
            total_non_normalized_count += total_non_normalized_batch_count
            roles_enqueued_count += roles_enqueued_batch_count

        # Disconnect from RabbitMQ
        if ENQUEUE_IDS:
            RabbitMQPublisher.disconnect()

    except Exception:
        _log(f'Error normalizing {role_type_in_logs}', 'error')
        _log(traceback.format_exc(), 'error')
        raise

    return (to_normalize_count, normalized_count, written_count, total_non_normalized_count)



def _get_roles_to_normalize(role_field: str, db_read_batch_size: int) -> List[Role]:
    """
    Read roles to normalize from Catho's database.

    :param str role_field: Role type to read from database, either CV roles or work experience roles
    :param int db_read_batch_size: Read this many entries from database at a time
    :return List: List of roles to normalize, retrieved from database
    """

    if role_field not in ['cv_role', 'work_exp_role']:
        _log(f'Unknown role type: {role_field}', 'error')
        return []

    if not db_read_batch_size:
        _log('DB read batch size not set', 'error')
        return []

    roles_to_normalize = []

    if role_field == 'cv_role':
        mysql_read_query = _DB_GET_CV_ROLES_QUERY
    elif role_field == 'work_exp_role':
        mysql_read_query = _DB_GET_WORK_EXPERIENCE_ROLES_QUERY

    # Get role data from database
    roles_data = _get_specific_roles_to_normalize(db_read_batch_size, mysql_read_query)

    # Transform role data read from database into Role objects
    if roles_data:
        if role_field == 'cv_role':
            roles_to_normalize = [ Role(row[0], row[1], row[2]) for row in roles_data ]
        elif role_field == 'work_exp_role':
            roles_to_normalize = [ Role(row[0], row[1], row[3], work_exp_id=row[2]) for row in roles_data ]
    else:
        roles_to_normalize = []

    return roles_to_normalize



@retry(stop=stop_after_attempt(5), wait=wait_fixed(5))
def _get_specific_roles_to_normalize(db_read_batch_size: int, mysql_read_query: str) -> List[Tuple]:
    """
    Read roles to normalize from Catho's database, using the received query.

    :param int db_read_batch_size: Read this many entries from database at a time
    :param str mysql_read_query: MySQL query to retrieve roles from database
    :return List: List of roles to normalize, retrieved from database
    """

    if not db_read_batch_size:
        _log('DB read batch size not set', 'error')
        return []

    if not mysql_read_query:
        _log('DB read query not set', 'error')
        return []

    global _DB_READ_CONNECTION
    global _DB_READ_CURSOR
    global _DB_DATE_FILTER_STEPS
    global _DB_CURRENT_DATE_FILTER_INDEX
    global _DB_RERUN_READ_QUERY
    global _DB_DATE_FILTERING_DONE

    roles_to_normalize = []

    try:

        if not _DB_READ_CONNECTION or not _DB_READ_CURSOR:

            _log('Connect to database to read data', 'debug')
            mysql_user = _DB_USER
            mysql_password = _DB_PASSWORD
            mysql_host = _DB_READ_HOST
            _log(f'MySQL user: {mysql_user}', 'debug')
            _log(f'MySQL host: {mysql_host}', 'debug')
            _DB_READ_CONNECTION = pymysql.connect(
                user = mysql_user,
                password = mysql_password,
                host = mysql_host,
                connect_timeout = 300)
            _log('Connected to database to read data', 'debug')

            _log('Setting a long session timeout', 'debug')
            _DB_READ_CONNECTION.query('SET @@session.wait_timeout = 1800')
            _DB_READ_CURSOR = _DB_READ_CONNECTION.cursor()

        else:

            _log('Reconnect to database to read data, if needed', 'debug')
            _DB_READ_CONNECTION.ping()

        # Either it's the first run or the date filter was updated
        if _DB_RERUN_READ_QUERY:

            _log(f'Retrieving non-normalized database roles from {_DB_DATE_FILTER_STEPS_PRETTY_NAME[_DB_CURRENT_DATE_FILTER_INDEX]}', 'info')
            _log('Execute retrieve query in database', 'debug')
            mysql_read_query = mysql_read_query.format(
                date_filter=_DB_DATE_FILTER_STEPS[_DB_CURRENT_DATE_FILTER_INDEX],
                limit_clause=_DB_READ_LIMIT_CLAUSE
            )
            _log(f'Retrieve query: {mysql_read_query}', 'debug')
            _DB_READ_CURSOR.execute(mysql_read_query)
            _log('Executed retrieve query in database', 'debug')

            _DB_RERUN_READ_QUERY = False

        _log(f'Retrieve at most {db_read_batch_size} rows', 'debug')
        batch_rows = _DB_READ_CURSOR.fetchmany(db_read_batch_size)

        if batch_rows:
            _log(f'Rows returned by database: {len(batch_rows)}', 'debug')
            roles_to_normalize = [ row for row in batch_rows ]
        else:
            _log('No rows returned by database', 'debug')
            roles_to_normalize = []

            # No rows were returned with the current date filter
            # Move to next date filter
            if _DB_CURRENT_DATE_FILTER_INDEX+1 < len(_DB_DATE_FILTER_STEPS):
                _DB_CURRENT_DATE_FILTER_INDEX = _DB_CURRENT_DATE_FILTER_INDEX + 1
                if _SLEEP_SECS_BETWEEEN_DATE_RANGES:
                    _log(f'Waiting {_SLEEP_SECS_BETWEEEN_DATE_RANGES}s...', 'info')
                    time.sleep(_SLEEP_SECS_BETWEEEN_DATE_RANGES)
            # Or, if it was the last one, mark date filtering as done
            else:
                _DB_CURRENT_DATE_FILTER_INDEX = 0
                _DB_DATE_FILTERING_DONE = True
            # Either way, next time this method is called the read query should be run again
            _DB_RERUN_READ_QUERY = True

    except Exception:
        mysql_read_query = mysql_read_query.format(
            date_filter=_DB_DATE_FILTER_STEPS[_DB_CURRENT_DATE_FILTER_INDEX],
            limit_clause=_DB_READ_LIMIT_CLAUSE
        )
        _log(f'Error retrieving roles from database. Current query: {mysql_read_query})', 'error')
        _log(traceback.format_exc(), 'error')
        raise

    return roles_to_normalize



@retry(stop=stop_after_attempt(5), wait=wait_fixed(5))
def _is_part_of_ab_test_group(user_id: int, ab_test_group: str) -> bool:
    """
    Check if a user ID is part of a specific AB test group.

    :param int user_id: User ID to check
    :param str ab_test_group: AB test group to check if user belongs to
    :return bool: True if user ID belongs to AB test group, false otherwise
    """

    if not user_id:
        _log('Empty user ID - returning false', 'error')
        return False

    if not ab_test_group:
        _log('Empty AB test group - returning false', 'error')
        return False

    if not _AB_TEST_ENABLED:
        _log('AB test not enabled - returning false', 'error')
        return False

    try:

        ab_api_host = _AB_TEST_API_HOST
        ab_api_test_name = _AB_TEST_API_NAME
        ab_api_url = f'http://{ab_api_host}/v1/ab/{ab_api_test_name}/candidate/{user_id}'
        _log(f'AB Test API URL: {ab_api_url}', 'debug')

        headers = {}
        ab_api_auth = _AB_TEST_API_AUTH
        if ab_api_auth:
            headers = {
                'Authorization': ab_api_auth,
                'Content-type': 'application/json',
                'Cache-Control': 'no-cache'
                }

        response = requests.post(ab_api_url, headers=headers)
        _log(f'AB Test API response: {response.text}', 'debug')

        if response.status_code == 200:
            ab_side = response.json().get('ab_test_group', '')
            return str(ab_side) == str(ab_test_group)

    except Exception:
        _log(f'Error checking if user {user_id} is part of {ab_test_group} group of AB test - returning false', 'error')
        _log(traceback.format_exc(), 'error')

    return False



@retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
def _get_normalized_roles(role_field: str, roles: List[Role]) -> List[Role]:
    """
    Get normalized roles from Role Normalization API.

    :param str role_field: Role type being normalized, either CV or work experience roles
    :param List roles: List of roles to normalize, retrieved from database
    :return List: List of normalized roles, returned by the Role Normalization API
    """

    if role_field not in ['cv_role', 'work_exp_role']:
        _log(f'Unknown role type: {role_field}', 'error')
        return []

    if not roles:
        _log('No roles to normalize', 'error')
        return []

    roles_normalized = []

    try:

        request_origin = ''
        if role_field == 'cv_role':
            request_origin = 'routine_cv_role'
        elif role_field == 'work_exp_role':
            request_origin = 'routine_work_exp_role'

        role_norm_api_host = _ROLE_NORM_API_HOST
        role_norm_api_url = f'http://{role_norm_api_host}/v1/role_normalization/catho'
        _log(f'Role Normalization API URL: {role_norm_api_url}', 'debug')

        headers = {'Content-type': 'application/json'}
        role_norm_api_auth = _ROLE_NORM_API_AUTH
        if role_norm_api_auth:
            headers = {
                'Authorization': role_norm_api_auth,
                'Content-type': 'application/json',
                'Cache-Control': 'no-cache'
                }

        payload = {
            'titles': [
                role.role
                for role in roles
                if role
            ],
            'origin': request_origin
        }

        response = requests.post(role_norm_api_url, headers=headers, data=json.dumps(payload))
        _log(f'Role Normalization API response: {response.text}', 'debug')

        if response.status_code == 200:

            api_normalized_roles = response.json()
            for role in roles:
                api_normalized_role = api_normalized_roles.get(role.role)

                # The Role Normalization API can return more than one ID for each role successfully normalized
                # This happens if the role sent to the API is compound - e.g., "Secretaria/Recepcionista"
                # Use the first one if more than one ID is returned
                if api_normalized_role:
                    role.role_id = api_normalized_role[0]['role_id']
                    roles_normalized.append(role)

    except Exception:
        _log(f'Error normalizing roles via Role Normalization API: {roles}', 'error')
        _log(traceback.format_exc(), 'error')
        raise

    return roles_normalized



def _write_normalized_roles(role_field: str, roles: List[Role]) -> int:
    """
    Write normalized roles to Catho's database.

    :param str role_field: Role type to write to database, either CV roles or work experience roles
    :param List roles: List of roles to write to database, returned by the Role Normalization API
    :return int: Number of roles written to database
    """

    if role_field not in ['cv_role', 'work_exp_role']:
        _log(f'Unknown role type: {role_field}', 'error')
        return 0

    if not roles:
        _log('No roles to normalize', 'error')
        return 0

    if role_field == 'cv_role':

        # Compose CV role insert query
        insert_inner_select_clauses = [f'SELECT {roles[0].cv_id} AS cur_id, {roles[0].role_id} AS cargo_id']
        insert_inner_select_clauses.extend(
            [
                f'UNION ALL SELECT {role.cv_id}, {role.role_id}'
                for role in roles[1:]
            ]
        )
        mysql_insert_query = _DB_INSERT_CV_ROLE_QUERY.format(
            cv_role_table=_DB_CV_WRITE_TABLE,
            select_with_values=' '.join(map(str, insert_inner_select_clauses))
        )

        # Compose CV role update query
        update_case_conditions = [
            f'WHEN {role.cv_id} THEN {role.role_id}'
            for role in roles
        ]
        update_ids = [role.cv_id for role in roles]
        mysql_update_query = _DB_UPDATE_CV_ROLE_QUERY.format(
            cv_role_table=_DB_CV_WRITE_TABLE,
            case_conditions=' '.join(map(str, update_case_conditions)),
            cv_ids=','.join(map(str, update_ids))
        )

    elif role_field == 'work_exp_role':

        # Compose work experience role insert query
        insert_inner_select_clauses = [f'SELECT {roles[0].work_exp_id} AS curexpprof_id, {roles[0].role_id} AS cargo_id']
        insert_inner_select_clauses.extend(
            [
                f'UNION ALL SELECT {role.work_exp_id}, {role.role_id}'
                for role in roles[1:]
            ]
        )
        mysql_insert_query = _DB_INSERT_WORK_EXPERIENCE_ROLE_QUERY.format(
            work_exp_parent_table=_DB_WORK_EXP_PARENT_TABLE,
            work_exp_role_table=_DB_WORK_EXP_WRITE_TABLE,
            select_with_values=' '.join(map(str, insert_inner_select_clauses))
        )

        # Compose work experience role update query
        update_case_conditions = [
            f'WHEN {role.work_exp_id} THEN {role.role_id}'
            for role in roles
        ]
        update_ids = [role.work_exp_id for role in roles]
        mysql_update_query = _DB_UPDATE_WORK_EXPERIENCE_ROLE_QUERY.format(
            work_exp_role_table=_DB_WORK_EXP_WRITE_TABLE,
            case_conditions=' '.join(map(str, update_case_conditions)),
            work_exp_ids=','.join(map(str, update_ids))
        )

    return _write_specific_normalized_roles(roles, mysql_insert_query, mysql_update_query)



def _write_specific_normalized_roles(roles: List[Role], mysql_insert_query: str, mysql_update_query: str) -> int:
    """
    Write normalized roles to Catho's database, using the received query.

    :param List roles: List of roles to write to database, returned by the Role Normalization API
    :param str mysql_insert_query: MySQL query to insert roles in database
    :param str mysql_update_query: MySQL query to update roles in database
    :return int: Number of roles written to database
    """

    if not roles:
        _log('No normalized roles to write to database', 'error')
        return 0

    if not mysql_insert_query or not mysql_update_query:
        _log('DB insert or update query not set', 'error')
        return 0

    roles_inserted = 0
    roles_updated = 0
    roles_written = 0

    try:

        _log('Connect to database to write', 'debug')
        mysql_user = _DB_USER
        mysql_password = _DB_PASSWORD
        mysql_host = _DB_WRITE_HOST
        _log(f'MySQL user: {mysql_user}', 'debug')
        _log(f'MySQL host: {mysql_host}', 'debug')
        db_write_connection = pymysql.connect(
            user = mysql_user,
            password = mysql_password,
            host = mysql_host,
            connect_timeout = 300,
            autocommit = True)
        db_write_cursor = db_write_connection.cursor()
        _log('Connected to database to write', 'debug')

        # Insert records not yet present in the roles table
        _log('Execute insert query in database', 'debug')
        _log(f'Insert query: {mysql_insert_query}', 'debug')
        if WRITE_NORM_ROLE:
            roles_inserted += db_write_cursor.execute(mysql_insert_query)
        _log(f'Executed insert query in database: {roles_inserted}', 'debug')

        # Update records in the roles table
        _log('Execute update query in database', 'debug')
        _log(f'Update query: {mysql_update_query}', 'debug')
        if WRITE_NORM_ROLE:
            roles_updated += db_write_cursor.execute(mysql_update_query)
        _log(f'Executed update query in database: {roles_updated}', 'debug')

        roles_written += roles_inserted
        roles_written += roles_updated

    except Exception:
        _log(f'Error writing normalized roles to database: {roles}', 'error')
        _log(traceback.format_exc(), 'error')
        raise
    finally:
        _log('Close write connection to database', 'debug')
        db_write_cursor.close()
        db_write_connection.close()
        _log('Closed write connection to database', 'debug')

    return roles_written



def _write_normalized_role_flags(roles: List[Role]) -> int:
    """
    Mark roles as updated in Catho's database.

    :param List roles: List of roles to mark as updated in database
    :return int: Number of roles marked as updated in database
    """

    if not roles:
        _log('No normalized role flags to write to database', 'error')
        return 0

    flags_upserted = 0

    try:

        _log('Connect to database to write', 'debug')
        mysql_user = _DB_USER
        mysql_password = _DB_PASSWORD
        mysql_host = _DB_FLAG_WRITE_HOST
        _log(f'MySQL user: {mysql_user}', 'debug')
        _log(f'MySQL host: {mysql_host}', 'debug')
        db_write_connection = pymysql.connect(
            user = mysql_user,
            password = mysql_password,
            host = mysql_host,
            connect_timeout = 300,
            autocommit = True)
        db_write_cursor = db_write_connection.cursor()
        _log('Connected to database to write', 'debug')

        # Compose role flag insert/update query
        none_to_zero = lambda value: value or 0
        mysql_insert_update_query = _DB_UPSERT_FLAG_QUERY.format(
            role_flag_table=_DB_FLAG_WRITE_TABLE,
            flag_values=', '.join(
                [
                    f'({none_to_zero(role.user_id)}, {none_to_zero(role.cv_id)}, {none_to_zero(role.work_exp_id)}, {none_to_zero(role.role_id)})'
                    for role in roles
                ]
            )
        )

        # Insert records not yet present in the roles table
        _log('Execute insert/update query in database', 'debug')
        _log(f'Insert/Update query: {mysql_insert_update_query}', 'debug')
        if WRITE_FLAG:
            flags_upserted += db_write_cursor.execute(mysql_insert_update_query)
        _log(f'Executed insert/update query in database: {flags_upserted}', 'debug')

    except Exception:
        _log(f'Error writing role flags to database: {roles}', 'error')
        _log(traceback.format_exc(), 'error')
        raise
    finally:
        _log('Close write connection to database', 'debug')
        db_write_cursor.close()
        db_write_connection.close()
        _log('Closed write connection to database', 'debug')

    return flags_upserted



def _enqueue_normalized_user_ids(role_field: str, roles: List[Role]) -> int:
    """
    Enqueue normalized roles into a RabbitMQ queue to be indexed by workers in RecSys Elasticsearch.

    :param str role_field: Role type to enqueue into RabbitMQ, either CV roles or work experience roles
    :param List roles: List of normalized roles, returned by the Role Normalization API
    :return int: Number of roles enqueued
    """

    if role_field not in ['cv_role', 'work_exp_role']:
        _log(f'Unknown role type: {role_field}', 'error')
        return 0

    if not roles:
        _log('No normalized roles to enqueue into RabbitMQ', 'error')
        return 0

    try:

        normalized_user_ids = list(set([role.user_id for role in roles]))
        normalized_user_ids_count = len(normalized_user_ids)

        # Enqueue user IDs to be indexed by RecSys indexer into Elasticsearch
        if ENQUEUE_IDS:
            queue_publisher = RabbitMQPublisher(
                _RABBITMQ_INDEX_USERS_ES_QUEUE,
                _RABBITMQ_HOST,
                _RABBITMQ_PORT,
                _RABBITMQ_USERNAME,
                _RABBITMQ_PASSWORD)
        queue_message = {
            'usr_ids': normalized_user_ids
        }
        _log(f'RabbitMQ message for queue {_RABBITMQ_INDEX_USERS_ES_QUEUE}: {json.dumps(queue_message, indent=4)}', 'debug')
        if ENQUEUE_IDS:
            queue_publisher.publish_msg(queue_message)

    except Exception:
        _log(f'Error enqueueing roles into RabbitMQ: {roles}', 'error')
        _log(traceback.format_exc(), 'error')
        raise

    return normalized_user_ids_count



if __name__ == '__main__':
    main()
