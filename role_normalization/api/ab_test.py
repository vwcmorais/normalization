import falcon
import random


class AbTestMockUp:

    """
    Handles AB Test API mock up requests.
    """

    def on_get(self, req, resp, ab_test_name, usr_id):

        # Random 500 error - 2% chance
        random_error = random.random() > 0.98
        if random_error:
            resp.status = falcon.HTTP_500
            return

        # AB Test API will return 404 for users that are not registered - 5% chance
        user_not_registered = random.random() > 0.93
        if user_not_registered:
            resp.status = falcon.HTTP_404
            resp.text = 'Candidate not found'
            return

        # Return a random AB test group
        resp.status = falcon.HTTP_200
        ab_test_group = random.choice(['a', 'aa', 'b'])
        resp.media = {
            "candidate_id": usr_id,
            "ab_test_name": ab_test_name,
            "ab_test_group": ab_test_group,
            "ab_test_algorithm": ('original' if ab_test_group in ['a', 'aa'] else 'variant_1'),
            "ab_test_configs": None
        }

    def on_post(self, req, resp, ab_test_name, usr_id):

        # Random error - 2% chance
        random_error = random.random() > 0.98
        if random_error:
            resp.status = falcon.HTTP_500
            return

        # Return a random AB test group
        resp.status = falcon.HTTP_200
        ab_test_group = random.choice(['a', 'aa', 'b'])
        resp.media = {
            "candidate_id": usr_id,
            "ab_test_name": ab_test_name,
            "ab_test_group": ab_test_group,
            "ab_test_algorithm": ('original' if ab_test_group in ['a', 'aa'] else 'variant_1'),
            "ab_test_configs": None
        }
