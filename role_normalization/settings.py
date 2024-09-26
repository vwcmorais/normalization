import base64
import boto3
import builtins
import json
import logbook
import os
from functools import wraps
from spectree import SpecTree


# Decorator to be used with lru_cache decorator in functions that have dict and/or list arguments
# Usage:
#   @lru_hash_mutable
#   @lru_cache
#   def function(d: dict = {}, l: list = []):
#       ...
def lru_hash_mutable(func):
    """
    Transform mutable dicts and lists into immutable, so they are compatible with lru_cache decorator.
    """
    class HashableDict(dict):
        def __hash__(self):
            return hash(frozenset(self.items()))
    class HashableList(list):
        def __hash__(self):
            return hash(tuple(self))
    @wraps(func)
    def wrapped(*args, **kwargs):
        args = tuple([HashableDict(arg) if isinstance(arg, dict) else HashableList(arg) if isinstance(arg, list) else arg for arg in args])
        kwargs = {k: HashableDict(v) if isinstance(v, dict) else HashableList(v) if isinstance(v, list) else v for k, v in kwargs.items()}
        wrapped.cache_info = func.cache_info
        wrapped.cache_clear = func.cache_clear
        return func(*args, **kwargs)
    return wrapped
builtins.lru_hash_mutable = lru_hash_mutable

#
# Environment settings
#

env = 'dev'
if os.getenv('ROLE_NORM_ENV'):
    env = os.getenv('ROLE_NORM_ENV')

aws_region = 'us-east-1'
if os.getenv('AWS_DEFAULT_REGION'):
    aws_region = os.getenv('AWS_DEFAULT_REGION')

env_secrets = json.loads('{}')
if os.getenv('ROLE_NORM_SECRETS'):
    env_secrets = json.loads(os.getenv('ROLE_NORM_SECRETS'))

aws_sm_prefix = 'role-normalization/api'

#
# AWS Secrets Manager settings
#

def get_secret( prefix, topic, env, key ):
    if topic in env_secrets and key in env_secrets[topic]:
        return env_secrets[topic][key]
    secret = ''
    aws_sm_client = boto3.session.Session().client(
        service_name='secretsmanager',
        region_name=aws_region)
    secret_id = prefix + '/' + env
    try:
        aws_response = aws_sm_client.get_secret_value(
            SecretId = secret_id
        )
        if 'SecretString' in aws_response:
            secrets_str = aws_response['SecretString']
        else:
            secrets_str = base64.b64decode(aws_response['SecretBinary'])
        secrets = json.loads(secrets_str)
        secret = secrets[topic][key]
    except:
        logbook.exception()
        raise
    return secret

#
# MySQL settings
#

mysql_user = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'user')
mysql_passwd = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'password')
mysql_read_host = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'read_host')
mysql_write_host = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'write_host')
mysql_flag_write_host = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'flag_write_host')
mysql_cv_write_table = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'cv_write_table')
mysql_job_write_table = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'job_write_table')
mysql_work_exp_parent_table = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'work_exp_parent_table')
mysql_work_exp_write_table = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'work_exp_write_table')
mysql_flag_write_table = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'flag_write_table')
mysql_job_flag_write_table = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'job_flag_write_table')
mysql_read_limit_clause = lambda: '' if env == 'prod' else 'LIMIT 1000'

#for applies
mysql_read_applies_host = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'read_applies_host')
mysql_read_applies_table = lambda: get_secret(aws_sm_prefix, 'MySQL', env, 'read_applies_table')

#
# Role Normalization API settings
#

# Used to create docs and for payload validation
# Docs available at /doc/redoc and /doc/swagger
spec = SpecTree('falcon', title='Role Normalization API', version='v1', path='v1/role_normalization/catho/doc')

role_norm_api_host = lambda: get_secret(aws_sm_prefix, 'RoleNormalizationApi', env, 'host')
role_norm_api_auth = lambda: get_secret(aws_sm_prefix, 'RoleNormalizationApi', env, 'auth')
role_norm_api_user = lambda: get_secret(aws_sm_prefix, 'RoleNormalizationApi', env, 'user')
role_norm_api_password = lambda: get_secret(aws_sm_prefix, 'RoleNormalizationApi', env, 'password')



#
# Events API
#

events_usr_applies_url = lambda: get_secret(aws_sm_prefix, 'EventsApi', env, 'usr_applies_url')
events_job_applies_url = lambda: get_secret(aws_sm_prefix, 'EventsApi', env, 'job_applies_url')
# events_api_auth = lambda: get_secret(aws_sm_prefix, 'EventsApi', env, 'auth')
# events_api_user = lambda: get_secret(aws_sm_prefix, 'EventsApi', env, 'user')
# events_api_password = lambda: get_secret(aws_sm_prefix, 'EventsApi', env, 'password')

#
# AB test settings
#

ab_test_enabled = False
ab_test_api_host = lambda: get_secret(aws_sm_prefix, 'AbTestApi', env, 'host')
ab_test_api_auth = lambda: get_secret(aws_sm_prefix, 'AbTestApi', env, 'auth')
ab_test_api_name = lambda: get_secret(aws_sm_prefix, 'AbTestApi', env, 'test_name')
ab_test_group = 'b'

#
# RabbitMQ settings
#

rabbitmq_host = lambda: get_secret(aws_sm_prefix, 'RabbitMQ', env, 'host')
rabbitmq_port = lambda: get_secret(aws_sm_prefix, 'RabbitMQ', env, 'port')
rabbitmq_username = lambda: get_secret(aws_sm_prefix, 'RabbitMQ', env, 'user')
rabbitmq_password = lambda: get_secret(aws_sm_prefix, 'RabbitMQ', env, 'password')
rabbitmq_index_users_es_queue = 'indexer_users'
rabbitmq_index_jobs_es_queue = 'indexer_jobs'

#
# Aho-Corasick matching settings
#

aho_corasick_matching_enabled = True
aho_corasick_role_title_max_words = 50
aho_corasick_word_combinations_min_length = 1
aho_corasick_word_combinations_max_length = 10
# Words in this list should be normalized: lowercase, no accents, no special characters
aho_corasick_single_word_titles_blocklist = [
    'arquiteto', 'arquiteta', 'architect', 'arquitetura', 'architecture',
    'medico', 'medica',
    'fisico', 'fisica',
    'seguranca', 'security',
    'designer', 'design',
]

#
# Word2Vec matching settings
#

w2v_matching_enabled = False
w2v_word_combinations_min_length = 1
w2v_min_role_similarity = 0.9
w2v_starting_role_words = ['estagiario', 'trainee']

#
# Logging settings
#

# Check if log level was set in the environment
# Must be either CRITICAL, ERROR, WARNING, NOTICE, INFO, or DEBUG
valid_log_levels = ['CRITICAL', 'ERROR', 'WARNING', 'NOTICE', 'INFO', 'DEBUG', 'TRACE']
env_log_level = os.getenv('LOG_LEVEL', default='').upper()
if env_log_level not in valid_log_levels:
    env_log_level = None

# Role Normalization routine log level
routine_log_level = 'INFO'
if env_log_level:
    routine_log_level = env_log_level

# Role Normalization API log level
# Logging in Role Normalization API should use the handler and log level defined below.
# To do that use the following code in other Role Normalization API files:
#
#   import logbook
#   from role_normalization import settings
#   logger = logbook.Logger(__name__)
#   settings.logger_group.add_logger(logger)
#
# And log messages using logger.debug(), logger.info(), etc.

# Role Normalization API log handler, prints log messages to stderr
logbook.StderrHandler().push_application()

# Role Normalization API log group, sets the log level for all loggers belonging to it - defaults to INFO
logger_group = logbook.LoggerGroup()
logger_group.level = logbook.INFO
if env_log_level:
    logger_group.level = logbook.lookup_level(env_log_level)

logger = logbook.Logger(__name__)
logger_group.add_logger(logger)

# Print current RecSys log level
logger.warning(f'Role Normalization log level set to {logbook.get_level_name(logger_group.level)}')
