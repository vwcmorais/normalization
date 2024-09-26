import bisect
import gzip
import json
import logbook
import nltk
import os
import pickle
import pkg_resources
import re2 as re
import tempfile
import unicodedata
from collections import OrderedDict
from functools import lru_cache
from symspellpy import SymSpell, Verbosity
from unidecode import unidecode

from role_normalization import settings


logger = logbook.Logger(__name__)
settings.logger_group.add_logger(logger)


class RoleNormalizer:

    """
    Normalize a given role title - remove stopwords, correct spelling, apply gazetteers, etc.
    """

    # Class attributes, shared by all instances
    special_character_regexes = []
    thesaurus_regexes = []
    conjugation_mapping = {}
    gender_regexes = []
    plural_regexes = []
    sorted_locations = []

    space_characters = [":", ",", ";", ".", "-", "–", "\t", "\\t"]
    special_characters = "\\()[]{}&#*+<>'\"/?!|^~@$%=`´¨_"
    line_break_characters = ["\r", "\n", "\\r", "\\n"]
    stop_words_to_keep = set(["sem"])
    additional_stop_words = set(["in", "of", "on"])

    stemmer = nltk.stem.RSLPStemmer()

    seniorities = set(["trainee", "junior", "pleno", "senior", "plena", "jr", "pl", "sr"])
    hierarchies = set(["lider", "chefe", "gerente", "supervisor", "coordenador", "supervisora", "coordenadora"])
    stopwords = set()

    # Instance attributes, object specific
    # dictionary
    # spell_checker


    def __init__(self, role_titles: list) -> None:

        """
        Initialize a role processor instance.

        Parameters:
        - role_titles : [str, ...] : Words extracted from these role titles will be added to the dictionary and to the spell checker
        """

        logger.info('Initializing RoleNormalizer instance')

        load_dir = os.path.dirname(os.path.realpath(__file__)) + '/load'
        gazetteers_dir = os.path.dirname(os.path.realpath(__file__)) + '/gazetteers/ptbr'

        self.stopwords.update(self._load_stopwords(gazetteers_dir + '/stopwords.txt'))
        self.stopwords = self.stopwords - self.stop_words_to_keep | self.additional_stop_words
        self.special_character_regexes.extend(self._load_mapping(gazetteers_dir + '/mapping_special_character_terms.txt'))
        self.thesaurus_regexes.extend(self._load_mapping(gazetteers_dir + '/mapping_thesaurus.txt'))
        self.conjugation_mapping.update(self._load_conjugation_mapping(gazetteers_dir + '/mapping_conjugation.txt'))
        self.gender_regexes.extend(self._load_mapping(gazetteers_dir + '/mapping_gender.txt'))
        self.plural_regexes.extend(self._load_plural_mapping(gazetteers_dir + '/mapping_plural.txt'))
        logger.info(f"Stop words list contains {len(self.stopwords)} words")
        logger.info(f"Special character terms mapping contains {len(self.special_character_regexes)} entries")
        logger.info(f"Synonyms mapping contains {len(self.thesaurus_regexes)} entries")
        logger.info(f"Verb conjugation mapping contains {len(self.conjugation_mapping)} entries")
        logger.info(f"Gender inflection mapping contains {len(self.gender_regexes)} entries")
        logger.info(f"Plural inflection mapping contains {len(self.plural_regexes)} entries")

        self.sorted_locations = sorted(self._load_locations(gazetteers_dir + '/locations.txt', role_titles))
        logger.info(f"Locations list contains {len(self.sorted_locations)} words")

        dictionary_filepath = load_dir + '/dictionary.pickle.gz'
        spell_checker_filepath = load_dir + '/spell_checker.pickle.gz'

        # Load dictionary and spell checker from files, if they exist
        if os.path.isfile(dictionary_filepath) and os.path.isfile(spell_checker_filepath):

            with gzip.open(dictionary_filepath, 'rb') as f:
                self.dictionary = pickle.load(f)
            with gzip.open(spell_checker_filepath, 'rb') as f:
                self.spell_checker = pickle.load(f)

            logger.info(f"Loaded dictionary with {len(self.dictionary)} words from file")
            logger.info(f"Loaded spell checker with {len(self.spell_checker.words)} words from file")

        # Else, create dictionary and spell checker from scratch and save them to files
        else:

            dictionary_ptbr = nltk.corpus.mac_morpho.words()
            dictionary_en = nltk.corpus.words.words()
            conjugation_ptbr = set()
            for k, v in self.conjugation_mapping.items():
                conjugation_ptbr.add(k)
                conjugation_ptbr.add(v)
            conjugation_ptbr = list(conjugation_ptbr)
            self.dictionary = set(
                dictionary_ptbr + dictionary_en +
                conjugation_ptbr +
                list(self.stopwords) +
                list(self.seniorities) + list(self.hierarchies) +
                self.sorted_locations
            )

            self._create_spell_checker()
            logger.info(f'Spell checker created with {len(self.spell_checker.words)} words')
            if role_titles:
                self._extract_and_add_to_dictioary(role_titles)
            thesaurus_words = self._extract_words_from_mapping(gazetteers_dir + '/mapping_thesaurus.txt')
            if thesaurus_words:
                self._extract_and_add_to_dictioary(thesaurus_words)
            special_character_words = self._extract_words_from_mapping(gazetteers_dir + '/mapping_special_character_terms.txt')
            if special_character_words:
                self._extract_and_add_to_dictioary(special_character_words)

            # Save dictionary and spell checker to files
            with gzip.open(dictionary_filepath, 'wb') as f:
                pickle.dump(self.dictionary, f)
            with gzip.open(spell_checker_filepath, 'wb') as f:
                pickle.dump(self.spell_checker, f)

            logger.info(f"Created dictionary with {len(self.dictionary)} words")
            logger.info(f"Created spell checker with {len(self.spell_checker.words)} words")

        logger.info('RoleNormalizer instance initialized')


    def _load_stopwords(self, stopwords_file: str) -> dict:
        # stopwords: {STOPWORD, ...}
        stopwords = set()
        with open(stopwords_file) as f:
            for line in f:
                if line.startswith('#'):
                    continue
                stopwords.add(line.strip())
        return stopwords


    def _load_mapping(self, mapping_file: str) -> list:
        # regexes: [('PATTERN', 'REPLACEMENT'), ...]
        regexes = []
        with open(mapping_file) as f:
            # mapping: {'BASE_WORD': ['VARIATION', ...], ...}
            mapping = OrderedDict()
            for line in f:
                if line.startswith('#'):
                    continue
                tokens = [token.strip() for token in line.lower().split(',')]
                if len(tokens) < 2:
                    logger.warning(f'Invalid line in {os.path.basename(mapping_file)}: {line.strip()}')
                    continue
                k = tokens[0]
                v = list(set(tokens[1:]))
                v.sort(key=lambda x: len(x.split()), reverse=True)
                mapping[k] = v
            for k, v in mapping.items():
                pattern = "|".join([re.escape(i) for i in v])
                pattern = r"( |^)+({})( |$)+".format(pattern)
                pattern = re.compile(pattern)
                replacement = r"\1{}\3".format(k)
                regexes.append((pattern, replacement))
        return regexes


    def _load_conjugation_mapping(self, conjugation_file: str) -> dict:
        # conjugation_mapping: {'CONJUGATED_VERB': 'BASE_VERB', ...}
        conjugation_mapping = {}
        with open(conjugation_file) as f:
            for line in f:
                if line.startswith('#'):
                    continue
                tokens = [token.strip() for token in line.lower().split(',')]
                if len(tokens) < 2:
                    logger.warning(f'Invalid line in {os.path.basename(conjugation_file)}: {line.strip()}')
                    continue
                v = tokens[0]
                for k in tokens[1:]:
                    conjugation_mapping[k] = v
        return conjugation_mapping


    def _load_plural_mapping(self, plural_file: str) -> list:
        # plural_regexes: [('PATTERN', 'REPLACEMENT'), ...]
        plural_regexes = []
        add_skip_mark_pattern = r"^(empregada|ingles|frances|leis|americanas|fisica|fisicas|educacaofisica|educadorafisica|instrutorafisica|fabrica|fabricas|bebida|bebidas|vida|vidas)$"
        add_skip_mark_pattern = re.compile(add_skip_mark_pattern)
        add_skip_mark_replacement = r"\1--"
        plural_regexes.append((add_skip_mark_pattern, add_skip_mark_replacement))
        with open(plural_file) as f:
            for line in f:
                if line.startswith('#'):
                    continue
                tokens = [token.strip() for token in line.lower().split(',')]
                if len(tokens) != 2:
                    logger.warning(f'Invalid line in {os.path.basename(plural_file)}: {line.strip()}')
                    continue
                pattern = r"(\D+)({})$".format(tokens[0])
                pattern = re.compile(pattern)
                replacement = r"\1{}".format(tokens[1])
                plural_regexes.append((pattern, replacement))
        remove_skip_mark_pattern = r"--"
        remove_skip_mark_pattern = re.compile(remove_skip_mark_pattern)
        remove_skip_mark_replacement = r""
        plural_regexes.append((remove_skip_mark_pattern, remove_skip_mark_replacement))
        return plural_regexes


    def _load_locations(self, locations_file: str, role_titles: list) -> list:
        # TODO: Don't include words that appear in normalized role titles
        # TODO: Don't include words that appear in the thesaurus
        # TODO: Don't include words that appear in the gender inflection list
        # TODO: Troublesome words present in location names: condominio, lider, quimica, and possibly many others
        # location_words: ['WORD', ...]
        location_words = self._extract_words_from_mapping(locations_file)
        # Don't include location words that are present in role tittles
        role_words = []
        separators = [
            re.escape(separator)
            for separator in list(set(
                [' '] + self.space_characters + [char for char in self.special_characters]
            ))
        ]
        for role_title in role_titles:
            for word in re.split('|'.join(separators), role_title):
                word = word.strip().lower()
                if word and len(word) >= 2 and word not in self.stopwords:
                    role_words.append(word)
        location_words = list(set(location_words) - set(role_words))
        return location_words


    def _create_spell_checker(self) -> SymSpell:
        # Load portuguese dictionary from spellchecker package
        pt_dict_gz = pkg_resources.resource_filename('spellchecker', 'resources/pt.json.gz')
        with gzip.open(pt_dict_gz, 'rb') as pt_dict_json:
            # pt_dict: {'WORD': FREQUENCY', ...}
            pt_dict = json.load(pt_dict_json)
        # pt_dict: [('WORD', FREQUENCY), ...], sorted by FREQUENCY
        pt_dict = sorted(pt_dict.items(), key=lambda kv: kv[1], reverse=True)

        # Create spell checker
        self.spell_checker = SymSpell()

        # Load portuguese dictionary into spell checker
        words = set()
        with tempfile.NamedTemporaryFile(prefix='dict_pt_', suffix='.txt', delete=False) as temp_file:
            for word, count in pt_dict:
                word = word.strip().lower()
                if not word or count < 1:
                    continue
                words.add(word)
                temp_file.write(f'{word} {count}\n'.encode('utf-8'))
            dict_path = temp_file.name
        with open(dict_path, 'r', encoding='utf-8') as temp_file:
            self.spell_checker.load_dictionary(temp_file.name, term_index=0, count_index=1)
        os.remove(dict_path)

        # Add portuguese dictionary words to RoleNormalizer dictionary
        self.dictionary = self.dictionary | words


    def _extract_and_add_to_dictioary(self, phrases: list) -> None:
        # Extract words and their frequency from phrases received, skipping stop words
        words = set()
        # words_freq_dict: {'WORD': FREQUENCY, ...]
        words_freq_dict = {}
        separators = [
            re.escape(separator)
            for separator in list(set(
                [' '] + self.space_characters + [char for char in self.special_characters]
            ))
        ]
        for phrase in phrases:
            for word in re.split('|'.join(separators), phrase):
                word = word.strip().lower()
                if word and len(word) >= 2 and word not in self.stopwords:
                    words.add(word)
                    words_freq_dict[word] = words_freq_dict.get(word, 0) + 1
        # words_freq: [('WORD', FREQUENCY), ...], sorted by FREQUENCY
        words_freq = sorted(words_freq_dict.items(), key=lambda kv: kv[1], reverse=True)

        # Add extracted words to dictionary
        self.dictionary = self.dictionary | words

        # Load words and their frequency into spell checker
        # If a word already exists in the spell checker's dictionary, it's frequency is updated not replaced
        with tempfile.NamedTemporaryFile(prefix='dict_words_', suffix='.txt', delete=False) as temp_file:
            for word, count in words_freq:
                word = word.strip().lower()
                if not word or count < 1:
                    continue
                temp_file.write(f'{word} {count}\n'.encode('utf-8'))
            dict_path = temp_file.name
        with open(dict_path, 'r', encoding='utf-8') as temp_file:
            self.spell_checker.load_dictionary(temp_file.name, term_index=0, count_index=1)
        os.remove(dict_path)

        logger.info(f'Spell checker updated with {len(words_freq)} words: {len(self.spell_checker.words)} words')


    def _extract_words_from_mapping(self, mapping_file: str) -> list:
        # mapping_words: {'WORD', ...}
        mapping_words = set()
        with open(mapping_file) as f:
            for line in f:
                if line.startswith('#'):
                    continue
                tokens = [token.strip() for token in line.lower().split(',')]
                for token in tokens:
                    words = token.split()
                    mapping_words.update(words)
        return list(mapping_words - self.stopwords)


    @lru_hash_mutable
    @lru_cache(maxsize=8192)
    def normalize(self, role_title: str,
                        correct_typos: bool = True,
                        stemming: bool = False,
                        remove_locations: bool = False,
                        normalize_conjugation: bool = True,
                        normalize_plural: bool = True,
                        normalize_gender: bool = True,
                        normalize_thesaurus: bool = True,
                        normalize_special_character_terms = True) -> tuple[str, list, list]:

        """
        Normalize a role title and return its normalized form and extracted seniorities
        and hierarchies.

        Parameters:
        - role_title                        : str  : Role title to be normalized
        - correct_typos                     : bool : Correct typos, default is True
        - stemming                          : bool : Stem words, default is False
        - remove_locations                  : bool : Remove location words, default is False
        - normalize_conjugation             : bool : Normalize verb conjugation, default is True
        - normalize_plural                  : bool : Normalize plural forms, default is True
        - normalize_gender                  : bool : Normalize gender inflection, default is True
        - normalize_thesaurus               : bool : Normalize thesaurus terms, default is True
        - normalize_special_character_terms : bool : Normalize terms containing special characters, default is True

        Returns:
        - str        : Normalized role title
        - [str, ...] : Extracted seniorities, if any
        - [str, ...] : Extracted hierarchies, if any
        """

        if not role_title or not isinstance(role_title, str):
            logger.warning(f'Invalid role title - empty or not a string: {role_title}')
            return '', [], []

        norm_role_title = role_title

        # Transform to lower case
        norm_role_title = norm_role_title.lower()
        logger.trace(f"normalize(): lower-cased: {norm_role_title}")

        # Remove line breaks
        norm_role_title = self._transform_text(norm_role_title, self.line_break_characters, " ")
        logger.trace(f"normalize(): line breaks replaced: {norm_role_title}")

        # Normalize terms containing special characters
        if normalize_special_character_terms:
            norm_role_title = self._normalize_by_mapping(norm_role_title, self.special_character_regexes)
            logger.trace(f"normalize(): normalized terms containing special characters: {norm_role_title}")

        # Replace space symbols
        norm_role_title = self._transform_text(norm_role_title, self.space_characters, " ")
        norm_role_title = re.sub(" +", " ", norm_role_title)
        norm_role_title = norm_role_title.strip()
        logger.trace(f"normalize(): multiple spaces replaced: {norm_role_title}")

        # Remove special symbols
        norm_role_title = self._transform_text(norm_role_title, list(self.special_characters), "")
        logger.trace(f"normalize(): special symbols removed: {norm_role_title}")

        # Correct typos
        if correct_typos:
            norm_role_title = self._correct_typos(norm_role_title)
            logger.trace(f"normalize(): typos corrected: {norm_role_title}")

        # Remove stop words
        norm_role_title = ' '.join([
            token
            for token in norm_role_title.split()
            if token not in self.stopwords
        ])
        logger.trace(f"normalize(): stop words removed: {norm_role_title}")

        # Remove Accents
        norm_role_title = unicodedata.normalize('NFKD', norm_role_title).encode("ASCII", "ignore")
        norm_role_title = self._fix_encoding(norm_role_title)
        logger.trace(f"normalize(): accents removed: {norm_role_title}")

        # Get seniorities and hierarchies
        seniorities = []
        hierarchies = []
        for token in norm_role_title.split():
            if token in self.seniorities:
                seniorities.append(token)
            if token in self.hierarchies:
                hierarchies.append(token)

        # Remove location words
        if remove_locations:
            norm_role_title = ' '.join([
                token
                for token in norm_role_title.split()
                if not self._in_sorted_list(token, self.sorted_locations)
            ])
            logger.trace(f"normalize(): locations removed: {norm_role_title}")

        # Normalize verb conjugation, plural, gender and synonyms
        if normalize_conjugation:
            norm_role_title = self._normalize_by_replace(norm_role_title, self.conjugation_mapping)
            logger.trace(f"normalize(): normalized verb conjugation: {norm_role_title}")

        if normalize_plural:
            norm_role_title = ' '.join([
                self._normalize_by_mapping(token, self.plural_regexes)
                for token in norm_role_title.split()
            ]).strip()
            logger.trace(f"normalize(): normalized plural inflection: {norm_role_title}")

        if normalize_gender:
            norm_role_title = self._normalize_by_mapping(norm_role_title, self.gender_regexes)
            logger.trace(f"normalize(): normalized gender inflection: {norm_role_title}")

        if normalize_thesaurus:
            norm_role_title = self._normalize_by_mapping(norm_role_title, self.thesaurus_regexes)
            logger.trace(f"normalize(): normalized based on thesaurus: {norm_role_title}")

        # Stemming
        if stemming:
            norm_role_title = ' '.join([
                self.stemmer.stem(token)
                for token in norm_role_title.split()
            ]).strip()
            logger.trace(f"normalize(): stemming applied: {norm_role_title}")

        return norm_role_title, seniorities, hierarchies


    def _correct_typos(self, text: str) -> str:

        text_words = text.split()
        logger.trace(f'_correct_typos(): text split: {text_words}')

        # Correct misspelled words in received text
        corrected_text = ''
        for word in text_words:
            corrected_word = word
            # Skip if word is present in the dictionary
            if word not in self.dictionary:
                # Get the most likely correction - smallest edit distance and highest term frequency
                correction = self.spell_checker.lookup(word, Verbosity.TOP, max_edit_distance=2)
                corrected_word = correction[0].term if correction else word
                logger.trace(f'_correct_typos(): spell correction, if any: {word} > {corrected_word}')
            corrected_text += corrected_word
            corrected_text += ' '

        logger.trace(f"_correct_typos(): original text: {text}")
        logger.trace(f"_correct_typos(): typos corrected: {corrected_text}")

        return corrected_text


    def _in_sorted_list(self, elem: any, sorted_list: list) -> bool:
        # Search a sorted list using binary search
        i = bisect.bisect_left(sorted_list, elem)
        return i != len(sorted_list) and sorted_list[i] == elem


    def _transform_text(self, text: str, symbols: list, replace: str) -> str:
        text_norm = text
        for symbol in symbols:
            text_norm = text_norm.replace(symbol, replace)
        return text_norm


    def _fix_encoding(self, text: str, encodings: list = None) -> str:
        if not encodings:
            encodings = ['utf-8', 'latin-1']
        if isinstance(text, (bytes, bytearray)):
            for enc in encodings:
                try:
                    return text.decode(enc)
                except AttributeError:
                    pass
            return unidecode(text)
        return text


    def _normalize_by_mapping(self, s: str, processed_mapping: list) -> str:
        # s: str
        # processed_mapping: [(re.Pattern, str), ...], with patterns and replacements
        new_s = s.strip()
        for pattern, replacement in processed_mapping:
            new_s = pattern.sub(replacement, new_s)
        return new_s.strip()


    def _normalize_by_replace(self, s: str, mapping: dict) -> str:
        # s: str
        # mapping: {str: str, ...}
        new_s = ""
        for w in s.strip().split():
            if w in mapping:
                w = mapping[w]
            new_s += w + " "
        return new_s.strip()
