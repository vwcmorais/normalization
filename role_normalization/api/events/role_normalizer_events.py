from datetime import datetime, timezone,timedelta
import json
import logbook
import pymysql
import requests
import time

from role_normalization import settings

logger = logbook.Logger(__name__)
settings.logger_group.add_logger(logger)

class DbConnection:
    def __init__(self,
            user,
            password,
            host,
            port=3306):

        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self._connect()

    def _connect(self):
        self.con = pymysql.connect(
            user = self.user,
            password = self.password,
            host = self.host,
            port = self.port,
            connect_timeout = 300)

    def check(self):
        try:
            self.con.ping(True)
        except Exception:
            logger.warning(f'Problem accessing connection at {self.host}. Creating new connection.')
            self._connect()
        
    def fetch_all(self, query):

        self.check()

        attempts = 3

        while attempts > 0:
            attempts -= 1
            try:
                cur = self.con.cursor()
                cur.execute(query)
                return cur.fetchall()
            except Exception as ex:
                if attempts < 1:
                    raise ex

    def batch_fetch_all(self, query, items, batch_size):
        result = []
        for i in range(0, len(items), batch_size):
            batch_items = items[i:i+batch_size]
            batch_query = query.format(",".join(map(str, batch_items)))
            result.update(self.fetch_all(query))
        return result

class RoleNormalizerEvents:

    """
    Infer (normalize) job/user role based on events (applies and contacts).
    """

    def __init__(self) -> None:

        """
        Initialize a role processor instance.

        Parameters:
        
        """
        logger.info('Initializing RoleNormalizerEvents instance')

        logger.info(f'Connecting to DB on {settings.mysql_read_host()}')

        self.db_con = DbConnection(
            user = settings.mysql_user(),
            password = settings.mysql_passwd(),
            host = settings.mysql_read_host())

        self.dw_con = DbConnection(
            user = settings.mysql_user(),
            password = settings.mysql_passwd(),
            host = settings.mysql_read_applies_host())

#    def _get_applies_origin(self, usr_ids: list, job_ids: list) -> list:
#        """
#        Retrieve apply origin from database.
#
#        Returns:
#        - [(int, str), ...] : List of tuples with role ID and title
#        """
#        logger.info(f'Recovering apply origin from db')
#        # Get ID and title of similar roles from database
#        # Check if ID and title are valid
#        # Order by ID to keep mappings consistent
#        usr_clause = f"env.ID_USRO IN ({usr_ids})"
#        if len(usr_ids) == 1:
#            usr_clause = f"env.ID_USRO = {usr_ids[0]}"
#
#        job_clause = f"AND env.ID_VAGA IN ({job_ids})"
#        if len(job_ids) == 1:
#            job_clause = f"AND env.ID_VAGA = {job_ids[0]}"
#
#        apply_origem_db_query = f"""
#            SELECT
#                env.ID_USRO as usr_id,
#                env.ID_VAGA as vag_id,
#                LOWER(tc.CD_CNAL_ENVO_CRRO) as envio_canal
#            FROM 
#                USER_AREA_BI.TB_VIZ_ENVIO_CURRICULO env
#            LEFT JOIN 
#                DWU.TB_ATR_ORIGEM_ENVIO_CURRICULO tc USING (ID_ORGM_ENVO_CRRO)
#            WHERE
#                env.ID_USRO IN ({usr_ids})
#                AND env.ID_VAGA IN ({job_ids})
#        """
#        return self.dw_con.fetch_all(apply_origem_db_query)
    
    def _get_jobs_contacts(self, job_ids: list, limit: int ) -> dict:
        """
        Retrieve contacts from database.

        Returns:
        - [(int, str), ...] : List of tuples with role ID and title
        """
        logger.info('Recovering Contacts from db')

        query = """
            SELECT
                f.vag_id AS vag_id,
                f.usr_id AS usr_id
            FROM 
                Data_Warehouse.f_contatos as f
            LEFT JOIN 
                Data_Warehouse.dim_data dd ON f.dim_data_contato_id = dd.dim_data_id
            WHERE
                f.vag_id IN ({})
        """
        if not job_ids:
            return {}

        # LIMIT {limit_contacts}
        batch_query = query.format(','.join(map(str,job_ids)))
        rows = self.dw_con.fetch_all(batch_query)
        r = {}
        for row in rows:
            job_id = row[0]
            usr_id = row[1]
            if job_id in r:
                r[job_id].append(usr_id)
            else:
                r[job_id] = [usr_id]
        return r
    
    def _get_jobs_roles(self, job_ids: list) -> dict:
        """
        Retrieve roles from database with job id.
        Input:
        - [int,...] : List of job IDs

        Returns:
        - {'123123': 321, '234234': 234, ... } : Dict of (str)job_id: (int)role_num
        """
        query = """
             SELECT
                v.vag_id as vag_id,
                vc.cargo_id AS cargo_id
            FROM conline.vag AS v
            LEFT JOIN conline.vag_cargo vc ON (v.vag_id=vc.vag_id)
            LEFT JOIN conline.cargo cc ON (vc.cargo_id=cc.cargo_id)
            WHERE v.vag_id IN ({})
        """
        if not job_ids:
            return {}

        batch_query = query.format(','.join(map(str,job_ids)))
        rows = self.db_con.fetch_all(batch_query)
        r = {}
        for row in rows:
            r[str(row[0])] = row[1]
        return r
    
    def _get_usrs_roles(self, usr_ids: list) -> dict:
        """
        Retrieve roles from database using user_ids.
        Input:
        - [int,...] : List of user ID

        Returns:
        - [(int, int), ...] : List of tuples with user ID and role ID
        """
        query = """
            SELECT
                c.usr_id as usr_id,
                vc.cargo_id AS cargo_id
            FROM conline.cur AS c
            LEFT JOIN conline.cur_cargo vc ON c.cur_id=vc.cur_id
            LEFT JOIN conline.cargo cc ON vc.cargo_id=cc.cargo_id
            WHERE c.usr_id in ({})
        """
        if not usr_ids:
            return {}

        batch_query = query.format(','.join(map(str,usr_ids)))
        rows = self.db_con.fetch_all(batch_query)
        r = {}
        for row in rows:
            r[str(row[0])] = row[1]
        return r

    def _get_last_users_applies_from_api(self, user_ids: list, limit_days=0, limit_applies=300) -> dict:
        """
        Get apply events from Events API of user or jobs.

        TODO: 
            - retrieve headers from file "role_normalization/api/settings.py
        Parameters:
        - [int, ...]: List of ids to retrieve data from API
        - str: type of IDs, "user" or "job"
        - int: number of days to limit apply retrieve
        - int: max number of applies per ID

        Returns:
        dict: List of applies from each id
        {
            "{user_id/job_id}": {
                "applies": [
                {
                    "company_id": "string",
                    "cv_id": "string",
                    "job_id": "string",
                    "profile_id": "string",
                    "recruiter_id": "string",
                    "timestamp": 0,
                    "user_id": "string"
                }, ...
                ]
            },..
        }
        """
        if not user_ids:
            logger.info('No user_ids to infer role', 'error')
            return []

        events_url = settings.events_usr_applies_url()
        
        api_events_response = []

        try:

            headers = {'Content-type': 'application/json'}
            # if events_api_auth:
            #     headers = {
            #         'Authorization': settings.events_api_auth(),
            #         }
            
            payload = {
                "days": limit_days,
                "limit": limit_applies,
                "origin": "role_inference_by_event",
                "user_ids": [str(id) for id in user_ids]
                }
            
            response = requests.post(events_url, headers=headers, data=json.dumps(payload))

            # logger.info(f'Events API response: {response.text}')
            logger.info(f'Events API response: ok')

            if response.status_code == 200:
                api_events_response = response.json()

        except Exception:
            logger.info(f'Error recovering applies via Events API: {user_ids}')
            raise

        return api_events_response

#    def _get_last_users_applies_from_db(self, user_ids: list, limit_days=0, limit_applies=10) -> dict:
#
#        limit_clause = ""
#        if limit_days > 0:
#            limit_clause = f" AND DT_ENVO_CRRO > DATE_SUB(NOW(), INTERVAL {limit_days} DAY)"
#
#        query = """
#        SELECT env.ID_USRO as usr_id, env.ID_VAGA as vag_id FROM
#        USER_AREA_BI.TB_VIZ_ENVIO_CURRICULO env LEFT JOIN DWU.TB_ATR_ORIGEM_ENVIO_CURRICULO tc USING
#        (ID_ORGM_ENVO_CRRO) WHERE env.ID_USRO IN ({})
#        """ + limit_clause
#
#        db_r = self.dw_con.batch_fetch_all(query, user_ids, 10)        
#        
#        r = {}
#        for row in db_r:
#            usr_id = row[0]
#            job_id = row[1]
#            if usr_id in r and len(r[usr_id]) < limit_applies:
#                r[usr_id].append(job_id)
#            else:
#                r[usr_id] = [job_id]
#
#        return r

    def _get_last_job_applies(self, job_ids: list, limit_days=0, limit_applies=10) -> dict:
        """
        Get apply events from Events API of user or jobs.

        TODO: 
            - retrieve headers from file "role_normalization/api/settings.py
        Parameters:
        - [int, ...]: List of ids to retrieve data from API
        - str: type of IDs, "user" or "job"
        - int: number of days to limit apply retrieve
        - int: max number of applies per ID

        Returns:
        dict: List of applies from each id
        {
            "{user_id/job_id}": {
                "applies": [
                {
                    "company_id": "string",
                    "cv_id": "string",
                    "job_id": "string",
                    "profile_id": "string",
                    "recruiter_id": "string",
                    "timestamp": 0,
                    "user_id": "string"
                }, ...
                ]
            },..
        }
        """
        if not job_ids:
            logger.info('No ids to infer role', 'error')
            return []

        events_url = settings.events_job_applies_url()
        
        api_events_response = []

        try:

            headers = {'Content-type': 'application/json'}
            # if events_api_auth:
            #     headers = {
            #         'Authorization': settings.events_api_auth(),
            #         }

            payload = {
                "days": limit_days,
                "job_ids": [str(id) for id in job_ids],
                "limit": limit_applies,
                "origin":  "role_inference_by_event"               
                }

            response = requests.post(events_url, headers=headers, data=json.dumps(payload))

            # logger.info(f'Events API response: {response.text}')
            logger.info(f'Events API response: ok')

            if response.status_code == 200:
                api_events_response = response.json()

        except Exception:
            logger.info(f'Error recovering applies via Events API: {job_ids}')
            raise

        return api_events_response

    def _most_frequent(self, role_id_list: list):
        """
        Function that receive a list of role id and return the most frequent element

        Parameters:
        - role_id_list: role id list 

        Returns:
        - int: Most frequent role id
        """
        if not role_id_list:
            return 0

        counter = 0
        num = 0
        for i in role_id_list:
            if i !=0 and not i is None: 
                curr_frequency = role_id_list.count(i)
                if(curr_frequency> counter):
                    counter = curr_frequency
                    num = i
        return num

    def normalize_usr_ids(self, usr_ids: list):

        """
        Infer usr_id roles and return its normalized based on apply events.

        Parameters:
        - usr_ids               : list : User ids with non normalized roles to be normalized
        
        Returns:
        - list       : Inferred role
        """

        if not usr_ids:
            return []
        
        # response variable
        inferred_roles = []
        
        # events variables
        limit_day = 0
        limit_applies = 200
        # retrieve last applies from api
        usrs_applies = self._get_last_users_applies_from_api(usr_ids,limit_day,limit_applies)

        a = time.time()
        
        jobs_list = []
        for usr_id in usrs_applies.keys():
            if 'applies' in usrs_applies[usr_id]:
                for usr_apply in usrs_applies[usr_id]['applies']:
                    jobs_list.append(usr_apply["job_id"])
        job_roles = {}
        if len(jobs_list) > 0:
            job_roles = self._get_jobs_roles(jobs_list)

        for usr_id in usr_ids:
            usr_id = str(usr_id)
            if usr_id in usrs_applies and 'applies' in usrs_applies[usr_id]:
                usr_roles = []
                for usr_apply in usrs_applies[usr_id]['applies']:
                    job_id = usr_apply["job_id"]
                    if job_id in job_roles:
                        usr_roles.append(job_roles[job_id])
                if len(usr_roles) > 0:
                    # infer new role_id based on most_frequent applies
                    inferred_roles.append([usr_id,self._most_frequent(usr_roles)])
                else:
                    logger.info(f'Role ID for usr {usr_id} not infered because we could get no role IDs for usr applies')
                    inferred_roles.append([usr_id,0])
            else:
                inferred_roles.append([usr_id,0])
                logger.info(f'Role ID for usr {usr_id} not infered because the apply list is empty')

        return inferred_roles
 
    def normalize_job_ids(self, job_ids: list):

        """
        Infer job roles and return its normalized based on apply events.

        Parameters:
        - job_ids               : list : Vag ids with non normalized roles to be normalized

        Returns:
        - list                  : Inferred role id 
        """

        if not job_ids:
            logger.info('No ids to infer role', 'error')
            return []
        
        # response variable
        inferred_roles = []
        jobs_found = []

        # events variables
        limit_day = 0
        limit_applies = 200
        limit_contacts = 200

        inference_type = ''

        contacts = self._get_jobs_contacts(job_ids, limit_contacts)

        usr_ids = []
        for job_id in contacts.keys():
            usr_ids.extend(contacts[job_id])

        usr_roles = self._get_usrs_roles(usr_ids)

        get_by_apply = []
        for job_id in job_ids:
            if job_id in contacts and len(contacts[job_id]) > 0:
                roles = []
                for usr_id in contacts[job_id]:
                    if usr_id in usr_roles:
                        roles.append(usr_roles[usr_id])
                if len(roles) > 0:
                    inferred_roles.append([job_id,self._most_frequent(roles)])
                    jobs_found.append(job_id)
                else:
                    get_by_apply.append(job_id)
            else:
                get_by_apply.append(job_id)


        jobs_applies = self._get_last_job_applies(get_by_apply,limit_day,limit_applies)
        applies = []
        ac = 0
        for job_id in jobs_applies.keys():
            if 'applies' in jobs_applies[job_id]:
                for job_apply in jobs_applies[job_id]['applies']:
                    applies.append(job_apply['user_id'])
                    ac += 1
        logger.debug(f"Got {str(ac)} applies for {str(len(jobs_applies))} jobs")
        
        applies_roles = self._get_usrs_roles(applies)
        
        logger.debug(f"Got {str(len(applies_roles))} user roles")

        for job_id in get_by_apply:
            roles = []
            if str(job_id) in jobs_applies and 'applies' in jobs_applies[str(job_id)]:
                for job_apply in jobs_applies[str(job_id)]['applies']:
                    usr_id = job_apply['user_id']
                    if usr_id in applies_roles:
                        roles.append(applies_roles[usr_id])
                    else:
                        logger.info(f"Got no roles for usr {str(usr_id)}")
            else:
                logger.debug(f"Got no applies for job {str(job_id)}")
            if len(roles) > 0:
                inferred_roles.append([job_id,self._most_frequent(roles)])
                jobs_found.append(job_id)
            else:
                inferred_roles.append([job_id,0])
        
        for job_id in job_ids:
            if job_id not in jobs_found:
                inferred_roles.append([job_id,0])

        return inferred_roles
