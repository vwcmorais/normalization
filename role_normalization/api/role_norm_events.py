import falcon
import json
import logbook
import re2 as re
from collections import OrderedDict
from enum import Enum
from pydantic import BaseModel, Field
from spectree import Response
from typing import List, Dict

from role_normalization import settings
from role_normalization.api.models.role_matcher import RoleMatcher
from role_normalization.api.events.role_normalizer_events import RoleNormalizerEvents


logger = logbook.Logger(__name__)
settings.logger_group.add_logger(logger)

spec = settings.spec


# URL parameters validation
class RequestParams(BaseModel):
    test: bool = Field(
        default=False,
        title='Request is a test',
        description='Marks request as a test.',
    )

# Response body validation
class NormalizedRole(BaseModel):
    role_title: str = Field(
        ...,
        title='Normalized role title',
        description="Normalized role title, present in Catho's database.",
        example='Recepcionista',
    )
    role_id: int = Field(
        ...,
        title='Normalized role ID',
        description="Normalized role ID, present in Catho's database.",
        example=1104,
    )
class ResponsePayload(BaseModel):
    __root__: Dict[str, NormalizedRole] = Field(
        ...,
        title='Normalized job or user IDs',
        description='Job or user IDs that could be normalized.',
        example={
            '123': {
                'role_title': 'Recepcionista',
                'role_id': 1104
            },
        },
    )

class JobRequestPayload(BaseModel):
    # Required fields are marked with "..."
    # Optional fields must have a default value
    job_ids: List[int] = Field(
        ...,
        title='Job IDs',
        description='Jobs that should be normalized based on events.',
        min_items=1,
        max_items=1000,
        example=[123, 456],
    )
    origin: str = Field(
        ...,
        title='Request origin',
        description="The system/app/page calling this api",
        example='vecstore_indexer',
    )

class JobRoleNormalizer:

    """
    Job Role Inference based on contacted/applied CV roles.
    """
    rne = RoleNormalizerEvents()

    @spec.validate(json=JobRequestPayload, query=RequestParams, resp=Response(HTTP_200=ResponsePayload, HTTP_403=None), tags=['role-normalization'])
    def on_post(self, req, resp):

        request_payload = req.context.get('json')
        job_ids = request_payload.job_ids # List of job_ids
        request_params = req.context.get('query')
        is_test = request_params.test == True

        logger.debug(f'Normalizing {len(job_ids)} job IDs based on events')
        resp_obj = {}

        new_roles = self.rne.normalize_job_ids(job_ids)
        for u,r in new_roles:
            resp_obj.update({
                str(u): {
                'role_title': '',
                'role_id': r
                }
            })

        #logger.debug(json.dumps(resp_obj,indent = 3))
        # Return 200 if one or more IDs were normalized
        if resp_obj:
            resp.status = falcon.HTTP_200
        # 204 otherwise
        else:
            resp.status = falcon.HTTP_204

        resp.media = resp_obj


class UserRequestPayload(BaseModel):
    # Required fields are marked with "..."
    # Optional fields must have a default value
    user_ids: List[int] = Field(
        ...,
        title='User IDs',
        description='Users that should be normalized based on events.',
        min_items=1,
        max_items=1000,
        example=[123, 456],
    )
    origin: str = Field(
        ...,
        title='Request origin',
        description="The system/app/page calling this api",
        example='vecstore_indexer',
    )

class UserRoleNormalizer:

    """
    User Role Inference based on applied job roles.
    """
    rne = RoleNormalizerEvents()

    @spec.validate(json=UserRequestPayload, query=RequestParams, resp=Response(HTTP_200=ResponsePayload, HTTP_403=None), tags=['role-normalization'])
    def on_post(self, req, resp):

        request_payload = req.context.get('json')
        user_ids = request_payload.user_ids
        request_params = req.context.get('query')
        is_test = request_params.test == True

        logger.debug(f'Normalizing {len(user_ids)} user IDs based on events')
        resp_obj = {}

        new_roles = self.rne.normalize_usr_ids(user_ids)
        for u,r in new_roles:
            resp_obj.update({
                str(u): {
                'role_title': '',
                'role_id': r
                }
            })

        logger.info(json.dumps(resp_obj,indent = 3))
        # Return 200 if one or more IDs were normalized
        if resp_obj:
            resp.status = falcon.HTTP_200
        # 204 otherwise
        else:
            resp.status = falcon.HTTP_204

        resp.media = resp_obj
