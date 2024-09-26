import unittest
import logbook

from role_normalization import settings
from role_normalization.api.models.role_matcher import RoleMatcher


logger = logbook.Logger(__name__)
settings.logger_group.add_logger(logger)


class NormalizeComponentTest(unittest.TestCase):

    def test(self):

        logger.info("Initializing roles dictionary")
        role_normalizer = RoleMatcher()

        # Test space removal
        logger.info("Testing space removal")
        self.assertEqual(role_normalizer.normalize("\tadvogado,júnior? "), role_normalizer.normalize("advogado júnior"))

        # Test case insensitiveness
        logger.info("Testing case insensitiveness")
        self.assertEqual(role_normalizer.normalize("AdVoGado JÚnior"), role_normalizer.normalize("advogado júnior"))

        # Test accents removal
        logger.info("Testing accents removal")
        self.assertEqual(role_normalizer.normalize("àdvõgádô júnior"), role_normalizer.normalize("advogado junior"))

        # Test gender inflection
        logger.info("Testing gender inflection")
        self.assertEqual(role_normalizer.normalize("advogada"), role_normalizer.normalize("advogado"))

        # Test special symbols removal
        logger.info("Testing special symbols removal")
        self.assertEqual(role_normalizer.normalize("ad&vog#ad*o"), role_normalizer.normalize("advogado"))

        # Test spelling correction
        logger.info("Testing spelling correction")
        self.assertEqual(role_normalizer.normalize("recepicionista"), role_normalizer.normalize("recepcionista"))

        # Test stop words removal
        logger.info("Testing stop words removal")
        self.assertEqual(role_normalizer.normalize("analista banco dados"), role_normalizer.normalize("analista de banco de dados"))

        # # Test stemming
        # logger.info("Testing stemming")
        # self.assertEqual(role_normalizer.normalize("advogado júnior"), role_normalizer.normalize("advogar como júnior"))

        # Test verb conjugation normalization
        logger.info("Testing verb conjugation normalization")
        self.assertEqual(role_normalizer.normalize("advogado júnior"), role_normalizer.normalize("advogaria como júnior"))

        # Test plural normalization
        logger.info("Testing plural inflection normalization")
        self.assertEqual(role_normalizer.normalize("advogado júnior"), role_normalizer.normalize("advogados junior"))

        # Test gender normalization
        logger.info("Testing gender inflection normalization")
        self.assertEqual(role_normalizer.normalize("advogado júnior"), role_normalizer.normalize("advogada junior"))

        # Test synonyms normalization
        logger.info("Testing synonyms replacement normalization")
        self.assertEqual(role_normalizer.normalize("advogado júnior"), role_normalizer.normalize("advocacia junior"))

        # Test Aho-Corasick matching
        logger.info("Testing Aho-Corasick matching")
        self.assertEqual(
            role_normalizer.normalize_and_match("advogado júnior")[1].role_id,
            role_normalizer.normalize_and_match("procuro vaga de advogado júnior em empresa")[1].role_id
        )

        # Test profile ID filtering
        logger.info("Testing profile ID filtering")
        self.assertEqual(
            role_normalizer.normalize_and_match("médico intensivista")[1].role_id,
            role_normalizer.normalize_and_match("médico intensivista", perfil_ids_filter=[6])[1].role_id
        )


if __name__ == '__main__':
    unittest.main()
