import gzip
import json
import logbook
import os
import pickle
import pymysql
from functools import lru_cache

from role_normalization import settings
from role_normalization.api.models.role_normalizer import RoleNormalizer
from role_normalization.api.models.aho_corasick_matcher import AhoCorasickMatcher
from role_normalization.api.models.w2v_matcher import W2vMatcher


logger = logbook.Logger(__name__)
settings.logger_group.add_logger(logger)


class ProcessedRole:

    """
    Stores a database role (role ID and title), its normalized form (processed title,
    seniorities and hierarchies) and related IDs (areap IDs, nivelh IDs, and perfil IDs).
    """

    # Mapping of perfil IDs to areap IDs and nivelh IDs
    # Populated during RoleMatcher initialization
    profile_id_mapping = {}

    def __init__(self, role_id, title, processed_title, seniorities, hierarchies, areap_ids, nivelh_ids, perfil_ids):
        self.role_id = role_id
        self.title = title
        self.processed_title = processed_title
        self.seniorities = seniorities
        self.hierarchies = hierarchies
        self.areap_ids = areap_ids
        self.nivelh_ids = nivelh_ids
        self.perfil_ids = perfil_ids

    def filter_by_perfil_ids(self, perfil_ids_filter: list) -> 'ProcessedRole':
        """
        Filter ProcessedRole areap IDs and nivelh IDs by perfil IDs.

        Parameters:
        - perfil_ids_filter  : list : List of perfil IDs to filter areap IDs and nivelh IDs

        Returns:
        - ProcessedRole : Filtered ProcessedRole
        """
        return ProcessedRole(
            self.role_id, self.title, self.processed_title,
            self.seniorities, self.hierarchies,
            self._filter_ids(self.areap_ids, perfil_ids_filter, 'areap_ids'),
            self._filter_ids(self.nivelh_ids, perfil_ids_filter, 'nivelh_ids'),
            self._filter_ids(self.perfil_ids, perfil_ids_filter, 'perfil_ids')
        )

    def _filter_ids(self, ids: list, perfil_ids_filter: list, id_type: str) -> list:
        """
        Filter a list of IDs by perfil IDs.

        Parameters:
        - ids                : list : List of IDs to filter
        - perfil_ids_filter  : list : List of perfil IDs to filter IDs
        - id_type            : str  : Type of IDs: areap_ids, nivelh_ids, or perfil_ids

        Returns:
        - list : Filtered list of IDs
        """
        if perfil_ids_filter:
            filtered_ids = []
            for perfil_id in perfil_ids_filter:
                if self.profile_id_mapping.get(perfil_id) and self.profile_id_mapping[perfil_id].get(id_type):
                    filtered_ids.extend(self.profile_id_mapping[perfil_id][id_type])
            return list(set.intersection(set(ids), set(filtered_ids)))
        else:
            return ids

    def __repr__(self):
        return f'ProcessedRole(role_id={self.role_id}, ' + \
            f'title="{self.title}", ' + \
            f'processed_title="{self.processed_title}", ' + \
            f'seniorities={self.seniorities}, ' + \
            f'hierarchies={self.hierarchies}, ' + \
            f'areap_ids={self.areap_ids}, ' + \
            f'nivelh_ids={self.nivelh_ids})' + \
            f'perfil_ids={self.perfil_ids})'


class RoleMatcher:

    """
    Normalize roles and match them against roles found in database. Singleton class.
    """

    _instance = None

    def __new__(cls) -> 'RoleMatcher':
        if cls._instance is None:
            cls._instance = super(RoleMatcher, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        try:

            logger.info('Initializing RoleMatcher instance')

            load_dir = os.path.dirname(os.path.realpath(__file__)) + '/load'
            gazetteers_dir = os.path.dirname(os.path.realpath(__file__)) + '/gazetteers/ptbr'

            # Load distinct database roles title from file, if it exists
            db_role_titles_filepath = load_dir + '/distinct_db_roles.pickle.gz'
            if os.path.isfile(db_role_titles_filepath):

                with gzip.open(db_role_titles_filepath, 'rb') as f:
                    db_role_titles = pickle.load(f)

                logger.info(f'Loaded {len(db_role_titles)} distinct role titles from file')

            # Else, get main and similar roles from database and save them to file
            else:

                # Get main and similar roles from database
                # db_*_roles: [(ROLE_ID, 'ROLE_TITLE'), ...]
                db_main_roles = self._get_db_main_roles()
                db_similar_roles = self._get_db_similar_roles()
                logger.info(f'Read {len(db_main_roles)} main roles from database')
                logger.info(f'Read {len(db_similar_roles)} similar roles from database')

                # Create a list with all role titles, used to create a dictionary of valid role words
                # db_role_titles: ['ROLE_TITLE', ...]
                db_role_titles = list(set([db_role[1] for db_role in db_main_roles + db_similar_roles]))

                # Save database role titles to file
                with gzip.open(db_role_titles_filepath, 'wb') as f:
                    pickle.dump(db_role_titles, f)

                logger.info(f'Loaded {len(db_role_titles)} distinct role titles from database')

            # Create a role processor, adding words found in role titles to its dictionary
            self.normalizer = RoleNormalizer(db_role_titles)

            # Create a mapping of role IDs to areap IDs, nivelh IDs and perfil IDs - fields in Catho's databases
            # role_id_mapping where all IDs are ints: {
            #   ROLE_ID: {
            #       'areap_ids': [AREAP_ID, ...],
            #       'nivelh_ids': [NIVELH_ID, ...],
            #       'perfil_ids': [PERFIL_ID, ...]
            #   }
            role_id_mapping = self._load_mapping(gazetteers_dir + '/mapping_cargo_id.json')
            # Create a mapping of perfil IDs to areap IDs and nivelh IDs, used for filtering based on perfil IDs
            # profile_id_mapping where all IDs are ints: {
            #   PERFIL_ID: {
            #       'areap_ids': [AREAP_ID, ...],
            #       'nivelh_ids': [NIVELH_ID, ...]
            #       'perfil_ids': [PERFIL_ID]
            #   }
            ProcessedRole.profile_id_mapping.update(self._load_mapping(gazetteers_dir + '/mapping_perfil_id.json'))

            # Load normalized main and similar role titles from files, if they exist
            norm_main_roles_mapping_filepath = load_dir + '/norm_main_roles_mapping.pickle.gz'
            norm_similar_roles_mapping_filepath = load_dir + '/norm_similar_roles_mapping.pickle.gz'
            if os.path.isfile(norm_main_roles_mapping_filepath) and os.path.isfile(norm_similar_roles_mapping_filepath):

                    with gzip.open(norm_main_roles_mapping_filepath, 'rb') as f:
                        self.norm_main_roles_mapping = pickle.load(f)
                    with gzip.open(norm_similar_roles_mapping_filepath, 'rb') as f:
                        self.norm_similar_roles_mapping = pickle.load(f)

                    logger.info(f'Loaded main roles\' mapping with {len(self.norm_main_roles_mapping)} entries from file')
                    logger.info(f'Loaded similar roles\' mapping with {len(self.norm_similar_roles_mapping)} entries from file')

            # Else, normalize main and similar role titles and save them to files
            else:

                # Normalize main and similar roles
                # norm_*_roles: [ProcessedRole, ...]
                norm_main_roles = []
                for i, db_role in enumerate(db_main_roles):
                    norm_role, seniorities, hierarchies = self.normalizer.normalize(db_role[1], correct_typos=False)
                    norm_main_roles.append(
                        ProcessedRole(
                            db_role[0], db_role[1],
                            norm_role, seniorities, hierarchies,
                            role_id_mapping.get(db_role[0], {}).get('areap_ids', []),
                            role_id_mapping.get(db_role[0], {}).get('nivelh_ids', []),
                            role_id_mapping.get(db_role[0], {}).get('perfil_ids', [])
                        )
                    )
                    if i % 100 == 0:
                        logger.debug(f'Normalized {i}/{len(db_main_roles)} main role titles')
                norm_similar_roles = []
                for i, db_role in enumerate(db_similar_roles):
                    norm_role, seniorities, hierarchies = self.normalizer.normalize(db_role[1], correct_typos=False)
                    norm_similar_roles.append(
                        ProcessedRole(
                            db_role[0], db_role[1],
                            norm_role, seniorities, hierarchies,
                            role_id_mapping.get(db_role[0], {}).get('areap_ids', []),
                            role_id_mapping.get(db_role[0], {}).get('nivelh_ids', []),
                            role_id_mapping.get(db_role[0], {}).get('perfil_ids', [])
                        )
                    )
                    if i % 100 == 0:
                        logger.debug(f'Normalized {i}/{len(db_similar_roles)} similar role titles')

                logger.info(f'Normalized {len(norm_main_roles)} main roles')
                logger.info(f'Normalized {len(norm_similar_roles)} similar roles')

                # Create mappings of normalized titles to ProcessedRole objects, used to check if a
                # given title matches a title found in the database
                # self.norm_*_roles_mapping: {'ROLE_TITLE': ProcessedRole(ROLE_ID, 'ROLE_TITLE'), ...}
                self.norm_main_roles_mapping = {}
                for norm_role in norm_main_roles:
                    if not self.norm_main_roles_mapping.get(norm_role.processed_title):
                        self.norm_main_roles_mapping[norm_role.processed_title] = norm_role
                self.norm_similar_roles_mapping = {}
                for norm_role in norm_similar_roles:
                    if (
                        not self.norm_main_roles_mapping.get(norm_role.processed_title)
                        and not self.norm_similar_roles_mapping.get(norm_role.processed_title)
                    ):
                        self.norm_similar_roles_mapping[norm_role.processed_title] = norm_role

                # Save normalized main and similar role titles to files
                with gzip.open(norm_main_roles_mapping_filepath, 'wb') as f:
                    pickle.dump(self.norm_main_roles_mapping, f)
                with gzip.open(norm_similar_roles_mapping_filepath, 'wb') as f:
                    pickle.dump(self.norm_similar_roles_mapping, f)

                logger.info(f'Created main roles\' mapping with {len(self.norm_main_roles_mapping)} entries')
                logger.info(f'Created similar roles\' mapping with {len(self.norm_similar_roles_mapping)} entries')

            self.aho_corasick_matching_enabled = settings.aho_corasick_matching_enabled
            if self.aho_corasick_matching_enabled:
                self.aho_corasick_matcher = AhoCorasickMatcher(self.norm_main_roles_mapping, self.norm_similar_roles_mapping)

            self.w2v_matching_enabled = settings.w2v_matching_enabled
            if self.w2v_matching_enabled:
                self.w2v_matcher = W2vMatcher(self.norm_main_roles_mapping, self.norm_similar_roles_mapping)

            logger.info('RoleMatcher instance initialized')

        # Raise an exception if an error occurs
        except Exception as e:
            logger.exception(f'Exception initializing RoleMatcher: {e}')
            raise e

    def _load_mapping(self, mapping_file: str) -> list:
        """
        Load a mapping from a JSON text file.

        Parameters:
        - mapping_file : str : Path to JSON mapping file

        Returns:
        - Mapping of IDs to dicts containing lists of IDs (areap_ids, nivelh_ids, and perfil_ids)
        """
        # Load JSON from file
        mapping_str = {}
        with open(mapping_file) as f:
            mapping_str = json.load(f)
        # Cast keys (IDs) to int
        mapping = {}
        for key_str in mapping_str.keys():
            value = mapping_str[key_str]
            mapping[int(key_str)] = value
        return mapping

    def _get_db_main_roles(self) -> list:
        """
        Retrieve main roles from database.

        Returns:
        - [(int, str), ...] : List of tuples with role ID and title
        """

        # Get ID and title of main roles from database
        # Check if ID and title are valid
        # Order by ID to keep mappings consistent
        main_roles_db_query = """
            SELECT
                cargo_id, titulo
            FROM
                conline.cargo
            WHERE
                (cargo_id IS NOT NULL AND cargo_id > 0)
                AND (titulo IS NOT NULL AND titulo != '')
            ORDER BY
                cargo_id
            ;
        """
        return self._get_db_roles(main_roles_db_query)

    def _get_db_similar_roles(self) -> list:
        """
        Retrieve similar roles from database.

        Returns:
        - [(int, str), ...] : List of tuples with role ID and title
        """

        # Get ID and title of similar roles from database
        # Check if ID and title are valid
        # Order by ID to keep mappings consistent
        similar_roles_db_query = """
            SELECT
                cargo_id, titulo
            FROM
                conline.cargo_titulo
            WHERE
                (cargo_id IS NOT NULL AND cargo_id > 0)
                AND (titulo IS NOT NULL AND titulo != '')
            ORDER BY
                cargo_id
            ;
        """
        return self._get_db_roles(similar_roles_db_query)

    def _get_db_roles(self, db_query: str) -> list:
        """
        Retrieve roles from database, using the received query.

        Parameters:
        - db_query : str : MySQL query to be executed

        Returns:
        - [(int, str), ...] : List of tuples with role ID and title
        """

        roles = []

        try:

            logger.debug('Retrieve database settings')
            db_user = settings.mysql_user()
            db_password = settings.mysql_passwd()
            db_host = settings.mysql_read_host()
            logger.debug('Retrieved database settings')

            logger.debug('Connect to database to read data')
            db_conn = pymysql.connect(
                user = db_user,
                password = db_password,
                host = db_host,
                connect_timeout = 300)
            logger.debug('Connected to database to read data')

            logger.debug('Execute retrieve query in database')
            logger.debug(f'Retrieve query: {db_query}')
            db_cursor = db_conn.cursor()
            db_cursor.execute(db_query)
            logger.debug('Executed retrieve query in database')

            rows = db_cursor.fetchall()

            if rows:
                logger.debug(f'Rows returned by database: {len(rows)}')
                roles = [row for row in rows]
            else:
                logger.debug('No rows returned by database')
                roles = []

        except Exception:
            logger.exception('Error retrieving roles from database')
            raise

        return roles

    def normalize(self, role_title: str) -> str:
        """
        Normalize a role title.

        Parameters:
        - role_title : str : Role title to be normalized

        Returns:
        - str : Normalized role title
        """
        return self.normalizer.normalize(role_title)

    @lru_hash_mutable
    @lru_cache(maxsize=8192)
    def normalize_and_match(self, role_title: str, perfil_ids_filter: list = None) -> tuple[str, ProcessedRole, str]:
        """
        Normalize a role title and match it against role titles found in database.

        Parameters:
        - role_title        : str  : Role title to be normalized and matched against database roles
        - perfil_ids_filter : list : List of perfil IDs to filter normalized roles

        Returns:
        - str           : Normalized role title
        - ProcessedRole : Database role that matches this normalized role title, if any
        - str           : Match type, if any - either "database", "ahocorasick", or "word2vec"
        """
        norm_title, _, _ = self.normalizer.normalize(role_title)
        db_norm_role = None
        match_type = None

        logger.debug(f'Normalized role title: {norm_title}')

        if perfil_ids_filter:
            logger.debug(f'Perfil IDs filter: {perfil_ids_filter}')

        # Try to match the whole role title
        logger.debug(f'Trying database match...')
        db_norm_role = self.norm_main_roles_mapping.get(norm_title) or \
            self.norm_similar_roles_mapping.get(norm_title)
        if db_norm_role:
            if perfil_ids_filter:
                if not set.intersection(set(perfil_ids_filter), set(db_norm_role.perfil_ids)):
                    return norm_title, None, None
                else:
                    match_type = 'database'
                    return norm_title, db_norm_role.filter_by_perfil_ids(perfil_ids_filter), match_type
            else:
                match_type = 'database'
                return norm_title, db_norm_role, match_type

        # Try to match word sequences of the role title using Aho-Corasick
        if self.aho_corasick_matching_enabled:
            logger.debug(f'Trying Aho-Corasick match...')
            matched_role = self.aho_corasick_matcher.match(norm_title)
            if matched_role:
                db_norm_role = self.norm_main_roles_mapping.get(matched_role) or \
                    self.norm_similar_roles_mapping.get(matched_role)
                if perfil_ids_filter:
                    if not set.intersection(set(perfil_ids_filter), set(db_norm_role.perfil_ids)):
                        return norm_title, None, None
                    else:
                        match_type = 'ahocorasick'
                        return norm_title, db_norm_role.filter_by_perfil_ids(perfil_ids_filter), match_type
                else:
                    match_type = 'ahocorasick'
                    return norm_title, db_norm_role, match_type

        # Try to find a similar role using Word2Vec
        if self.w2v_matching_enabled:
            logger.debug(f'Trying Word2Vec match...')
            matched_role = self.w2v_matcher.match(norm_title)
            if matched_role:
                db_norm_role = self.norm_main_roles_mapping.get(matched_role) or \
                    self.norm_similar_roles_mapping.get(matched_role)
                if perfil_ids_filter:
                    if not set.intersection(set(perfil_ids_filter), set(db_norm_role.perfil_ids)):
                        return norm_title, None, None
                    else:
                        match_type = 'word2vec'
                        return norm_title, db_norm_role.filter_by_perfil_ids(perfil_ids_filter), match_type
                else:
                    match_type = 'word2vec'
                    return norm_title, db_norm_role, match_type

        return norm_title, db_norm_role, match_type
