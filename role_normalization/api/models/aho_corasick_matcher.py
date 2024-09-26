import ahocorasick
import logbook
from itertools import combinations
from collections import OrderedDict

from role_normalization import settings


logger = logbook.Logger(__name__)
settings.logger_group.add_logger(logger)


class AhoCorasickMatcher(object):

    """
    Match a given role to a database role using the Aho-Corasick algorithm.
    """

    separator = None

    def __init__(self, norm_main_roles : dict, norm_similar_roles : dict) -> None:
        """
        Create an Aho-Corasick automaton to be used for matching.
        """

        try:

            logger.info('Initializing AhoCorasickMatcher instance')

            # Add normalized main and similar roles to Aho-Corasick automaton
            self.automaton = ahocorasick.Automaton()
            self.separator = ';'
            for norm_role in norm_main_roles:
                self.automaton.add_word(self.separator + norm_role + self.separator, self.separator + norm_role + self.separator)
            logger.info(f'Added {len(norm_main_roles)} main roles to automaton')
            for norm_role in norm_similar_roles:
                self.automaton.add_word(self.separator + norm_role + self.separator, self.separator + norm_role + self.separator)
            logger.info(f'Added {len(norm_similar_roles)} similar roles to automaton')
            self.automaton.make_automaton()

            self.role_title_max_words = settings.aho_corasick_role_title_max_words
            logger.info(f'Max words used in matching: {self.role_title_max_words}')

            self.word_combinations_min_length = settings.aho_corasick_word_combinations_min_length
            self.word_combinations_max_length = settings.aho_corasick_word_combinations_max_length
            logger.info(f'Word sequence length used in matching: '
                        f'{self.word_combinations_min_length}-{self.word_combinations_max_length}')

            self.single_word_titles_blocklist = set(settings.aho_corasick_single_word_titles_blocklist)
            logger.info(f'Single word titles blocklist ({len(self.single_word_titles_blocklist)}): {self.single_word_titles_blocklist}')

            logger.info('AhoCorasickMatcher instance initialized')

        # Raise an exception if an error occurs
        except Exception as e:
            logger.exception(f'Exception initializing AhoCorasickMatcher: {e}')
            raise e

    def match(self, norm_title: str) -> str:
        """
        Tries to match word sequences of a given role title to a role title found in
        the database, using the Aho-Corasick algorithm. Returns the database
        normalized role title that matched the longest word sequence in the received
        role title.
        """

        logger.debug('Aho-Corasick matching for normalized title: ' + norm_title)
        matched_role = None

        # Split the normalized role title into words and limit the number of words
        norm_title_split = norm_title.split()
        norm_title_split = norm_title_split[0:self.role_title_max_words]

        # Get sequential word combinations from the normalized role title
        norm_title_combinations = [
            norm_title_split[i:j]
            for i, j in combinations(range(len(norm_title_split)+1), 2)
            if self.word_combinations_min_length <= j-i <= self.word_combinations_max_length
        ]

        # Remove duplicated combinations, keeping the order
        norm_title_combinations_dedup = OrderedDict()
        for combination in norm_title_combinations:
            norm_title_combinations_dedup[tuple(combination)] = None
        norm_title_combinations = [
            list(combination_tuple)
            for combination_tuple in norm_title_combinations_dedup.keys()
        ]

        # Remove single word combinations that are in the blocklist
        norm_title_combinations = [
            combination
            for combination in norm_title_combinations
            if len(combination) > 1 or combination[0] not in self.single_word_titles_blocklist
        ]

        # Sort combinations by length, keeping the order
        norm_title_combinations.sort(key=len, reverse=True)

        logger.debug(f'Normalized title word combinations '
                     f'(min length {self.word_combinations_min_length}, '
                     f'max_length: {self.word_combinations_max_length}): '
                     f'{norm_title_combinations}')

        # Check if any of the combinations match a normalized database role title
        for norm_title_combination in norm_title_combinations:
            norm_title_substr = ' '.join(map(str, norm_title_combination))
            needle = self.separator + norm_title_substr + self.separator
            if list(self.automaton.iter_long(needle)):
                matched_role = norm_title_substr
                logger.debug(f'Match found ({len(norm_title_combination)} word(s)): {norm_title_substr}')
                break

        return matched_role
