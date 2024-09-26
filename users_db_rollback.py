import click
import pymysql
import traceback
from typing import List, Tuple
from datetime import datetime, timezone

from role_normalization import settings



"""
Role Normalization database rollback:
Based on the log database table we keep, rollback all normalized roles.
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



def _log(log_message: str, log_level: str) -> None:
    """
    Print log message.

    :param str log_message: Message to log
    :param str log_level: Message log level
    """

    # If message is empty, log and return
    if not log_message.strip():
        _log(f'Empty log message: log_message = "{str(log_message)}", log_level = "{str(log_level)}"', 'error')
        return

    log_levels = ['critical', 'error', 'warning', 'notice', 'info', 'debug']

    # If log level is not one of the above, log and return
    if log_level not in log_levels:
        _log(f'Invalid log level: log_message = "{str(log_message)}", log_level = "{str(log_level)}"', 'error')
        return

    # If message log level is of lower priority than _LOG_LEVEL, return
    if log_levels.index(log_level) > log_levels.index(_LOG_LEVEL):
        return

    formatted_log_message = '[' + str(datetime.now(timezone.utc).isoformat()[:-9] + 'Z') + '] '
    formatted_log_message += (str(log_level).upper() + ':').ljust(9) + ' '
    formatted_log_message += str(log_message)

    print(formatted_log_message)



#
# Enable/Disable flags, to be used during development
# If disabled, queries are just printed, not executed
#

ROLLBACK_NORM_ROLE = False

#
# Logging settings
#

_LOG_LEVEL = settings.routine_log_level.lower()
if _LOG_LEVEL not in ['critical', 'error', 'warning', 'notice', 'info', 'debug']:
    _LOG_LEVEL = 'info'
_log('Populating local variables with values from AWS Secrets Manager', 'info')

#
# MySQL settings
#

_START_DATE='2022-03-01'
_END_DATE='2022-05-31'

# Query to retrieve normalized CV roles
_DB_GET_NORM_CV_ROLES_QUERY = """
    SELECT
        usr_id,
        cur_id
    FROM
        {role_norm_log_table}
    WHERE
        curexpprof_id = 0
        {date_condition}
"""

# Query to retrieve normalized work experience roles
_DB_GET_NORM_WORK_EXP_ROLES_QUERY = """
    SELECT
        usr_id,
        cur_id,
        curexpprof_id
    FROM
        {role_norm_log_table}
    WHERE
        curexpprof_id != 0
        {date_condition}
"""

# CV role table
_DB_CV_WRITE_TABLE = settings.mysql_cv_write_table()

# Query to rollbak CV roles in the CV roles table
_DB_ROLLBACK_CV_ROLE_QUERY = """
    UPDATE IGNORE
        {cv_role_table}
    SET
        cargo_id = 0
    WHERE
        cur_id IN ({cv_ids})
    ;
"""

# Work experience role table
_DB_WORK_EXP_WRITE_TABLE = settings.mysql_work_exp_write_table()

# Query to rollbak work experience roles in the work experience roles table
_DB_ROLLBACK_WORK_EXP_ROLE_QUERY = """
    UPDATE IGNORE
        {work_exp_role_table}
    SET
        cargo_id = 0
    WHERE
        curexpprof_id IN ({work_exp_ids})
    ;
"""

# MySQL read connection and cursor, shared between methods
_DB_READ_CONNECTION = None
_DB_READ_CURSOR = None

# MySQL connection settings
_DB_USER = settings.mysql_user()
_DB_PASSWORD = settings.mysql_passwd()
_DB_READ_HOST = settings.mysql_flag_write_host()
_DB_READ_TABLE = settings.mysql_flag_write_table()
_DB_WRITE_HOST = settings.mysql_write_host()



@click.command()
@click.option('-drs', '--db-read-batch-size', default=5000, help='Read this many entries from database at a time. Default: 5000')
@click.option('-dws', '--db-write-batch-size', default=250, help='Write this many entries to database at a time. Default: 250')
def main(db_read_batch_size: int, db_write_batch_size: int):
    _log(f'Parameter db_read_batch_size = {db_read_batch_size}', 'debug')
    _log(f'Parameter db_write_batch_size = {db_write_batch_size}', 'debug')
    _role_normalization_rollback(db_read_batch_size, db_write_batch_size)



def _role_normalization_rollback(db_read_batch_size: int, db_write_batch_size: int) -> None:
    """
    Rollback CV and work experience roles previously normalized on Catho's databases.

    :param int db_read_batch_size: Read this many entries from database at a time
    :param int db_write_batch_size: Write this many entries to database at a time
    """

    _log('Rollback CV roles', 'info')
    to_rollback_count, rolled_back_count = _specific_role_normalization_rollback('cv_role', db_read_batch_size, db_write_batch_size)
    _log(f'CV roles rolled-back: {rolled_back_count}/{to_rollback_count}', 'info')

    _log('Rollback work experience roles', 'info')
    to_rollback_count, rolled_back_count = _specific_role_normalization_rollback('work_exp_role', db_read_batch_size, db_write_batch_size)
    _log(f'work experience roles rolled-back: {rolled_back_count}/{to_rollback_count}', 'info')



def _specific_role_normalization_rollback(role_field: str, db_read_batch_size: int, db_write_batch_size: int) -> Tuple[int, int]:
    """
    Rollback specific role type previously normalized on Catho's databases.

    :param str role_field: Role type to rollback, either CV roles or work experience roles
    :param int db_read_batch_size: Read this many entries from database at a time
    :param int db_write_batch_size: Write this many entries to database at a time
    :return Tuple[int, int]: Count of roles to rollback and count of roles rolled-back
    """

    if role_field not in ['cv_role', 'work_exp_role']:
        _log(f'Unknown role type: {role_field}', 'error')
        return 0

    if not db_read_batch_size:
        _log('DB read batch size not set', 'error')
        return 0

    if not db_write_batch_size:
        _log('DB write batch size not set', 'error')
        return 0

    global _DB_READ_CONNECTION
    global _DB_READ_CURSOR

    to_rollback_count = 0
    rolled_back_count = 0

    if role_field == 'cv_role':
        role_type_in_logs = 'CV roles'
    elif role_field == 'work_exp_role':
        role_type_in_logs = 'work experience roles'

    try:

        while True:

            # Get batch of roles to rollback
            _log(f'Get batch of {role_type_in_logs} to rollback', 'info')
            roles_to_rollback = _get_roles_to_rollback(role_field, db_read_batch_size)
            _log(f'Got batch of {role_type_in_logs} to rollback: {len(roles_to_rollback)}', 'info')

            # Stop once all batches have been processed
            if not roles_to_rollback:
                _log('Close read connection to database', 'debug')
                if _DB_READ_CURSOR:
                    _DB_READ_CURSOR.close()
                    _DB_READ_CURSOR = None
                if _DB_READ_CONNECTION:
                    _DB_READ_CONNECTION.close()
                    _DB_READ_CONNECTION = None
                _log('Closed read connection to database', 'debug')
                break

            to_rollback_batch = []

            to_rollback_batch_count = 0
            rolled_back_batch_count = 0

            # For each role to rollback
            for role in roles_to_rollback:

                to_rollback_batch_count += 1

                # Gather roles in batches to be rolled-back
                to_rollback_batch.append(role)

                # Rollback batch of roles
                if len(to_rollback_batch) == db_write_batch_size:
                    _log(f'Batch of {role_type_in_logs} to rollback: {len(to_rollback_batch)}', 'info')
                    rolled_back_batch_count = _rollback_roles(role_field, to_rollback_batch)
                    _log(f'Batch of {role_type_in_logs} rolled-back: {rolled_back_batch_count}', 'info')
                    to_rollback_batch = []

            # Rollback the last batch of roles
            if len(to_rollback_batch) > 0:
                _log(f'Batch of {role_type_in_logs} to rollback: {len(to_rollback_batch)}', 'info')
                rolled_back_batch_count = _rollback_roles(role_field, to_rollback_batch)
                _log(f'Batch of {role_type_in_logs} rolled-back: {rolled_back_batch_count}', 'info')

            to_rollback_count += to_rollback_batch_count
            rolled_back_count += rolled_back_batch_count

    except Exception:
        _log(f'Error rolling-back {role_type_in_logs}', 'error')
        _log(traceback.format_exc(), 'error')
        raise

    return (to_rollback_count, rolled_back_count)



def _get_roles_to_rollback(role_field: str, db_read_batch_size: int) -> List:
    """
    Read roles to rollback from Catho's database.

    :param str role_field: Role type to read from database, either CV roles or work experience roles
    :param int db_read_batch_size: Read this many entries from database at a time
    :return List: List of roles to rollback, retrieved from database
    """

    if role_field not in ['cv_role', 'work_exp_role']:
        _log(f'Unknown role type: {role_field}', 'error')
        return []

    if not db_read_batch_size:
        _log('DB read batch size not set', 'error')
        return []

    roles_to_rollback = []

    if role_field == 'cv_role':
        mysql_read_query = _DB_GET_NORM_CV_ROLES_QUERY.format(
            role_norm_log_table=_DB_READ_TABLE,
            date_condition=f"AND data_atualizacao BETWEEN '{_START_DATE}' AND '{_END_DATE}'" if _START_DATE and _END_DATE else ''
        )
    elif role_field == 'work_exp_role':
        mysql_read_query = _DB_GET_NORM_WORK_EXP_ROLES_QUERY.format(
            role_norm_log_table=_DB_READ_TABLE,
            date_condition=f"AND data_atualizacao BETWEEN '{_START_DATE}' AND '{_END_DATE}'" if _START_DATE and _END_DATE else ''
        )

    # Get role data from database
    roles_data = _get_specific_roles_to_rollback(db_read_batch_size, mysql_read_query)

    # Transform role data read from database into Role objects
    if roles_data:
        if role_field == 'cv_role':
            roles_to_rollback = [ Role(row[0], row[1], None) for row in roles_data ]
        elif role_field == 'work_exp_role':
            roles_to_rollback = [ Role(row[0], row[1], None, work_exp_id=row[2]) for row in roles_data ]
    else:
        roles_to_rollback = []

    return roles_to_rollback



def _get_specific_roles_to_rollback(db_read_batch_size: int, mysql_read_query: str) -> List:
    """
    Read roles to rollback from Catho's database, using the received query.

    :param int db_read_batch_size: Read this many entries from database at a time
    :param str mysql_read_query: MySQL query to retrieve roles from database
    :return List: List of roles to rollback, retrieved from database
    """

    if not db_read_batch_size:
        _log('DB read batch size not set', 'error')
        return []

    if not mysql_read_query:
        _log('DB read query not set', 'error')
        return []

    global _DB_READ_CONNECTION
    global _DB_READ_CURSOR

    roles_to_rollback = []

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

            _log('Execute retrieve query in database', 'debug')
            _log(f'Retrieve query: {mysql_read_query}', 'debug')
            _DB_READ_CURSOR = _DB_READ_CONNECTION.cursor()
            _DB_READ_CURSOR.execute(mysql_read_query)
            _log('Executed retrieve query in database', 'debug')

        _log(f'Retrieve at most {db_read_batch_size} rows', 'debug')
        batch_rows = _DB_READ_CURSOR.fetchmany(db_read_batch_size)

        if batch_rows:
            _log(f'Rows returned by database: {len(batch_rows)}', 'debug')
            roles_to_rollback = [ row for row in batch_rows ]
        else:
            _log('No rows returned by database', 'debug')
            roles_to_rollback = []

    except Exception:
        _log('Error retrieving roles from database', 'error')
        _log(traceback.format_exc(), 'error')
        raise

    return roles_to_rollback



def _rollback_roles(role_field: str, roles: List) -> int:
    """
    Rollback roles previously normalized on Catho's database.

    :param str role_field: Role type to rollback, either CV roles or work experience roles
    :param List roles: List of roles to rollback
    :return int: Number of roles rolled-back
    """

    if role_field not in ['cv_role', 'work_exp_role']:
        _log(f'Unknown role type: {role_field}', 'error')
        return 0

    if not roles:
        _log('No roles to rollback', 'error')
        return 0

    if role_field == 'cv_role':

        # Compose CV role rollback query
        rollback_ids = [role.cv_id for role in roles]
        mysql_rollback_query = _DB_ROLLBACK_CV_ROLE_QUERY.format(
            cv_role_table=_DB_CV_WRITE_TABLE,
            cv_ids=','.join(map(str, rollback_ids))
        )

    elif role_field == 'work_exp_role':

        # Compose work experience role rollback query
        rollback_ids = [role.work_exp_id for role in roles]
        mysql_rollback_query = _DB_ROLLBACK_WORK_EXP_ROLE_QUERY.format(
            work_exp_role_table=_DB_WORK_EXP_WRITE_TABLE,
            work_exp_ids=','.join(map(str, rollback_ids))
        )

    return _rollback_specific_roles(roles, mysql_rollback_query)



def _rollback_specific_roles(roles: List, mysql_rollback_query: str) -> int:
    """
    Write normalized roles to Catho's database, using the received query.

    :param List roles: List of roles to rollback
    :param str mysql_rollback_query: MySQL query to rollback roles
    :return int: Number of roles rolled-back
    """

    if not roles:
        _log('No roles to rollback', 'error')
        return 0

    if not mysql_rollback_query:
        _log('DB rollback query not set', 'error')
        return 0

    roles_rolled_back = 0

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

        # Rollback records in the roles table
        _log('Execute rollback query in database', 'debug')
        _log(f'Rollback query: {mysql_rollback_query}', 'debug')
        if ROLLBACK_NORM_ROLE:
            roles_rolled_back += db_write_cursor.execute(mysql_rollback_query)
        _log(f'Executed rollback query in database: {roles_rolled_back}', 'debug')

    except Exception:
        _log(f'Error rolling-back normalized roles in database: {roles}', 'error')
        _log(traceback.format_exc(), 'error')
        raise
    finally:
        _log('Close write connection to database', 'debug')
        db_write_cursor.close()
        db_write_connection.close()
        _log('Closed write connection to database', 'debug')

    return roles_rolled_back



if __name__ == '__main__':
    main()
