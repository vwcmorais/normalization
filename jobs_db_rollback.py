import click
import pymysql
import traceback
from typing import List, Tuple
from datetime import datetime, timezone

from role_normalization import settings



"""
Role Normalization database rollback:
Based on the log database table we keep, rollback all normalized job roles.
"""



# Represents a role that's associated with a specific job
class Role:

    def __init__(self, job_id, role, role_id=None):
        self.job_id = job_id
        self.role = role
        self.role_id = role_id

    def __repr__(self):
        return f'Role(job_id={self.job_id}, role={self.role}, role_id={self.role_id})'



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

_START_DATE='2023-06-12'
_END_DATE='2023-06-12'

# Query to retrieve normalized job roles
_DB_GET_NORM_JOB_ROLES_QUERY = """
    SELECT
        vag_id
    FROM
        {role_norm_log_table}
    WHERE
        {date_condition}
"""

# Job role table
_DB_JOB_WRITE_TABLE = settings.mysql_job_write_table()

# Query to rollbak job roles in the job roles table
_DB_ROLLBACK_JOB_ROLE_QUERY = """
    UPDATE IGNORE
        {job_role_table}
    SET
        cargo_id = 0
    WHERE
        vag_id IN ({job_ids})
    ;
"""

# MySQL read connection and cursor, shared between methods
_DB_READ_CONNECTION = None
_DB_READ_CURSOR = None

# MySQL connection settings
_DB_USER = settings.mysql_user()
_DB_PASSWORD = settings.mysql_passwd()
_DB_READ_HOST = settings.mysql_flag_write_host()
_DB_READ_TABLE = settings.mysql_job_flag_write_table()
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
    Rollback job roles previously normalized on Catho's databases.

    :param int db_read_batch_size: Read this many entries from database at a time
    :param int db_write_batch_size: Write this many entries to database at a time
    """

    _log('Rollback job roles', 'info')
    to_rollback_count, rolled_back_count = _specific_role_normalization_rollback(db_read_batch_size, db_write_batch_size)
    _log(f'Job roles rolled-back: {rolled_back_count}/{to_rollback_count}', 'info')



def _specific_role_normalization_rollback(db_read_batch_size: int, db_write_batch_size: int) -> Tuple[int, int]:
    """
    Rollback specific role type previously normalized on Catho's databases.

    :param int db_read_batch_size: Read this many entries from database at a time
    :param int db_write_batch_size: Write this many entries to database at a time
    :return Tuple[int, int]: Count of roles to rollback and count of roles rolled-back
    """

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

    try:

        while True:

            # Get batch of roles to rollback
            _log(f'Get batch of job roles to rollback', 'info')
            roles_to_rollback = _get_roles_to_rollback(db_read_batch_size)
            _log(f'Got batch of job roles to rollback: {len(roles_to_rollback)}', 'info')

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
                    _log(f'Batch of job roles to rollback: {len(to_rollback_batch)}', 'info')
                    rolled_back_batch_count = _rollback_roles(to_rollback_batch)
                    _log(f'Batch of job roles rolled-back: {rolled_back_batch_count}', 'info')
                    to_rollback_batch = []

            # Rollback the last batch of roles
            if len(to_rollback_batch) > 0:
                _log(f'Batch of job roles to rollback: {len(to_rollback_batch)}', 'info')
                rolled_back_batch_count = _rollback_roles(to_rollback_batch)
                _log(f'Batch of job roles rolled-back: {rolled_back_batch_count}', 'info')

            to_rollback_count += to_rollback_batch_count
            rolled_back_count += rolled_back_batch_count

    except Exception:
        _log(f'Error rolling-back job roles', 'error')
        _log(traceback.format_exc(), 'error')
        raise

    return (to_rollback_count, rolled_back_count)



def _get_roles_to_rollback(db_read_batch_size: int) -> List:
    """
    Read roles to rollback from Catho's database.

    :param int db_read_batch_size: Read this many entries from database at a time
    :return List: List of roles to rollback, retrieved from database
    """

    if not db_read_batch_size:
        _log('DB read batch size not set', 'error')
        return []

    global _DB_READ_CONNECTION
    global _DB_READ_CURSOR

    roles_to_rollback = []

    mysql_read_query = _DB_GET_NORM_JOB_ROLES_QUERY.format(
        role_norm_log_table=_DB_READ_TABLE,
        date_condition=f"data_atualizacao BETWEEN '{_START_DATE} 00:00:00' AND '{_END_DATE} 23:59:59'" if _START_DATE and _END_DATE else ''
    )

    # Get role data from database
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
            db_rows = [ row for row in batch_rows ]
        else:
            _log('No rows returned by database', 'debug')
            db_rows = []

    except Exception:
        _log(
            f'''Error retrieving roles from database. Current query: {
                mysql_read_query
            }''',
            'error'
        )
        _log(traceback.format_exc(), 'error')
        raise


    # Transform role data read from database into Role objects
    if db_rows:
        roles_to_rollback = [ Role(row[0], None) for row in db_rows ]
    else:
        roles_to_rollback = []

    return roles_to_rollback



def _rollback_roles(roles: List) -> int:
    """
    Rollback roles previously normalized on Catho's database.

    :param List roles: List of roles to rollback
    :return int: Number of roles rolled-back
    """

    if not roles:
        _log('No roles to rollback', 'error')
        return 0

    # Compose job role rollback query
    rollback_ids = [role.job_id for role in roles]
    mysql_rollback_query = _DB_ROLLBACK_JOB_ROLE_QUERY.format(
        job_role_table=_DB_JOB_WRITE_TABLE,
        job_ids=','.join(map(str, rollback_ids))
    )

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
