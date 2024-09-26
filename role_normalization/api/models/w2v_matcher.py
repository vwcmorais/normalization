import gzip
import logbook
import math
import numpy as np
import os
import pickle
from gensim.models import KeyedVectors
from itertools import combinations

from role_normalization import settings


logger = logbook.Logger(__name__)
settings.logger_group.add_logger(logger)


class W2vMatcher(object):

    """
    Match a given role to a database role using a Word2Vec model.
    """

    words_idf: dict = None
    words_w2v_model: KeyedVectors = None
    titles_w2v_model: KeyedVectors = None
    set_words_idf: set = None
    set_words_w2v_model: set = None

    def __init__(self, norm_main_roles : dict, norm_similar_roles : dict):
        """
        Load the Word2Vec words' model and IDF weights, both used to calculate
        embeddings. Also, create a Word2Vec roles' model with all database roles.
        """

        try:

            logger.info('Initializing W2vMatcher instance')

            # Load IDF weights dict
            words_idf_file_path = os.path.dirname(os.path.realpath(__file__)) + '/w2v/role_words_idf.pickle.gz'
            with gzip.open(words_idf_file_path, 'rb') as pickle_file:
                self.words_idf = pickle.load(pickle_file)
            self.words_idf = self.words_idf or {}

            logger.info(f"Role title words' IDF loaded - {len(self.words_idf)} words")

            # Load Word2Vec labels list, created using role title words
            words_w2v_labels_file_path = os.path.dirname(os.path.realpath(__file__)) + '/w2v/role_words_w2v_labels_30d.pickle.gz'
            with gzip.open(words_w2v_labels_file_path, 'rb') as pickle_file:
                words_w2v_labels = pickle.load(pickle_file)

            # Load Word2Vec embeddings numpy array, created using role title words
            words_w2v_embeddings_file_path = os.path.dirname(os.path.realpath(__file__)) + '/w2v/role_words_w2v_embeddings_30d.pickle.gz'
            with gzip.open(words_w2v_embeddings_file_path, 'rb') as pickle_file:
                words_w2v_embeddings = pickle.load(pickle_file)

            # Create Word2Vec words' model
            words_w2v_dimensions = words_w2v_embeddings.shape[1]
            self.words_w2v_model = KeyedVectors(words_w2v_dimensions)
            self.words_w2v_model.add_vectors(words_w2v_labels, words_w2v_embeddings)

            logger.info(f"Role title words' Word2Vec model loaded"
                f' - {len(self.words_w2v_model.vectors)} role vectors'
                f' with {self.words_w2v_model.vector_size} dimensions'
            )

            # Create sets to make it easier to check if a given word is
            # present in IDF and in Word2Vec words' model
            self.set_words_idf = set([
                word
                for word in self.words_idf
            ])
            self.set_words_w2v_model = set([
                word
                for word in self.words_w2v_model.index_to_key
            ])

            logger.info(f'Sets with Word2Vec and IDF words populated')

            # Add all database roles, main and similar, to a Word2Vec titles' model
            # Used to find the most similar role to the one received
            logger.info(f"Creating role titles' Word2Vec model...")
            self.titles_w2v_model = KeyedVectors(words_w2v_dimensions)
            for i, norm_role in enumerate(norm_main_roles):
                embedding, _ = self._calculate_embedding(norm_role)
                if embedding is not None:
                    self.titles_w2v_model.add_vectors(norm_role, embedding)
                if i % 100 == 0:
                    logger.debug(f'Added {i}/{len(norm_main_roles)} main roles')
            for i, norm_role in enumerate(norm_similar_roles):
                embedding, _ = self._calculate_embedding(norm_role)
                if embedding is not None:
                    self.titles_w2v_model.add_vectors(norm_role, embedding)
                if i % 100 == 0:
                    logger.debug(f'Added {i}/{len(norm_similar_roles)} similar roles')

            logger.info(f"Role titles' Word2Vec model created"
                f' - {len(self.titles_w2v_model.vectors)} role vectors'
                f' with {self.titles_w2v_model.vector_size} dimensions'
            )

            self.w2v_min_role_similarity = settings.w2v_min_role_similarity
            logger.info(f'Min Word2Vec role similarity: {self.w2v_min_role_similarity}')

            self.word_combinations_min_length = settings.w2v_word_combinations_min_length
            logger.info(f'Min word sequence length used in matching: {self.word_combinations_min_length}')

            self.w2v_starting_role_words = set(settings.w2v_starting_role_words)
            logger.info(f'Starting role words, used in matching: {self.w2v_starting_role_words}')

            logger.info('W2vMatcher instance initialized')

        # Raise an exception if an error occurs
        except Exception as e:
            logger.exception(f'Exception initializing W2vMatcher: {e}')
            raise e

    def _calculate_embedding(self, norm_title: str) -> list:
        """
        Given a role title, calculate and return it's embedding: sum of it's words'
        embeddings, using IDF as a weighting factor. Returns a numpy array and the
        total IDF weight, or None and zero in case of error.
        """
        try:

            embedding = None
            total_weight = 0

            norm_title = self._str_or_none(norm_title)
            if not norm_title:
                logger.debug(f'Role title is empty')
                return embedding, total_weight
            logger.trace(f'Normalized text: {norm_title}')

            norm_words = norm_title.split()

            # Check if all role title words are present in Word2Vec words' model and in IDF
            # Use set intersection for performance
            set_norm_words = set(norm_words)
            if self.set_words_w2v_model & set_norm_words != set_norm_words:
                words_diff = list(set_norm_words - self.set_words_w2v_model)
                logger.warning(f'Role title word(s) not found in Word2Vec model: {words_diff}')
                return embedding, total_weight
            if self.set_words_idf & set_norm_words != set_norm_words:
                words_diff = list(set_norm_words - self.set_words_idf)
                logger.warning(f'Role title word(s) not found in IDF: {words_diff}')
                return embedding, total_weight

            # Check if title total weight, calculated based on words' IDF, is greater than zero
            for word in set_norm_words:
                weight = self.words_idf.get(word, 1)
                total_weight += weight
            if total_weight == 0:
                logger.warning(f'Total weight of role title words is zero')
                return embedding, total_weight

            # Generate title embedding using words' IDF as weight
            embedding = np.zeros(self.words_w2v_model.vector_size, dtype=np.float128)
            for word in norm_words:
                weight = self.words_idf.get(word, 1)
                embedding = embedding + np.asarray(self.words_w2v_model.get_vector(word) * weight)
            embedding = np.asarray(embedding / total_weight)
            logger.trace(f'Role title embedding calculated: {embedding}')

        # Return None if an error occurs
        except Exception as e:
            logger.exception(f'Exception calculating role title embedding: {e}')
            embedding = None
            total_weight = 0

        return embedding, total_weight


    def _str_or_none(self, value) -> str:
        """
        Return value cast to string or None if value is None or an empty string.
        """
        try:
            if not str(value) or str(value) == 'None':
                return None
            return str(value)
        except:
            return None


    def _is_starting_role(self, norm_title_words: set) -> bool:
        return not norm_title_words.isdisjoint(self.w2v_starting_role_words)


    def match(self, norm_title: str) -> str:
        """
        Try to match a normalized role with database roles, using a Word2Vec model.
        Returns the most similar database normalized role title or None.
        """
        matched_role_title = None
        highest_similarity = 0
        highest_similarity_combination = []

        norm_title = self._str_or_none(norm_title)
        if not norm_title:
            logger.debug(f'Role title is empty')
            return matched_role_title

        norm_words = norm_title.split()
        set_norm_words = set(norm_words)

        # Check if received role is a starting role
        is_starting_role = self._is_starting_role(set_norm_words)

        # Calculate the embedding for each distinct word in the normalized title
        norm_word_to_embedding = {}
        norm_word_to_weight = {}
        for word in set_norm_words:
            embedding, weight = self._calculate_embedding(word)
            # Check if an embedding could be calculated for all normalized words
            if embedding is None:
                return matched_role_title
            norm_word_to_embedding[word] = embedding
            norm_word_to_weight[word] = weight

        # Get sequential word combinations from the normalized role title
        norm_title_combinations = [
            norm_words[i:j]
            for i, j in combinations(range(len(norm_words)+1), 2)
            if j-i >= self.word_combinations_min_length
        ]
        logger.debug(f'Normalized title word combinations (min length '
            f'{self.word_combinations_min_length}): {norm_title_combinations}')

        # For each combination of words
        for norm_title_combination in norm_title_combinations:

            # Calculate embedding for combination
            embedding = np.zeros(self.words_w2v_model.vector_size, dtype=np.float128)
            total_weight = 0
            for word in norm_title_combination:
                embedding += norm_word_to_embedding[word]
                total_weight += norm_word_to_weight[word]
            if total_weight == 0:
                logger.debug(f'Total weight for words combination is zero: {norm_title_combination}')
                continue
            embedding = np.asarray(embedding / total_weight)

            # Find closest match in Word2Vec role titles model
            matches = self.titles_w2v_model.similar_by_vector(embedding, topn=5)
            for match_title, match_similarity in matches:
                logger.debug(f'Role title word sequence: {norm_title_combination}')
                logger.debug(f'Match found: {match_title}')
                logger.debug(f'Match similarity: {match_similarity}')
                # Skip if matched role is a starting role and the received role is not
                if self._is_starting_role(set(match_title.split())) and not is_starting_role:
                    logger.debug(f'Skipping starting role match')
                    continue
                # Check if matched similarity is higher than the minimum
                if match_similarity > self.w2v_min_role_similarity:
                    # Check if it's at least 1% higher than the highest similarity found so far
                    if match_similarity - highest_similarity > 0.01:
                        matched_role_title = match_title
                        highest_similarity = match_similarity
                        highest_similarity_combination = norm_title_combination
                        logger.debug(f'Match found using Word2Vec: {matched_role_title}')
                    # If it's close to the highest similarity found so far, check if it's a longer sequence of words
                    elif math.isclose(match_similarity, highest_similarity, abs_tol=1e-2):
                        if len(norm_title_combination) > len(highest_similarity_combination):
                            matched_role_title = match_title
                            highest_similarity = match_similarity
                            highest_similarity_combination = norm_title_combination
                            logger.debug(f'Match found using Word2Vec: {matched_role_title}')
                else:
                    logger.debug(f'Low match similarity: {match_similarity}')
                    continue

        return matched_role_title
