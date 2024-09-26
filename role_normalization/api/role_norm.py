import falcon
import logbook
import re2 as re
from collections import OrderedDict
from pydantic import BaseModel, Field, validator
from spectree import Response
from typing import List, Dict

from role_normalization import settings
from role_normalization.api.models.role_matcher import RoleMatcher


logger = logbook.Logger(__name__)
settings.logger_group.add_logger(logger)

spec = settings.spec


class RequestParams(BaseModel):
    match_type: bool = Field(
        default=None,
        title='Match type',
        description='Include the match type for each normalization in the response body.'
            ' Optional. Expects "true" or "false".',
        example=True,
    )
    perfil_ids: str = Field(
        default=None,
        title='Profile IDs filter',
        description='Only return normalized roles that match at least one of these profile IDs.'
            ' If used, also filters areap and nivelh IDs returned. Include matching profile IDs'
            ' in the response body, in the perfil_ids field. Optional. Expects integers separated'
            ' by comma.',
        example='1,4',
    )
    @validator('perfil_ids')
    def perfil_ids_validation(cls, perfil_ids_str: str) -> list:
        if not perfil_ids_str:
            return []
        perfil_ids = []
        for perfil_id in perfil_ids_str.split(','):
            try:
                perfil_ids.append(int(perfil_id))
            except ValueError:
                raise ValueError(f'Perfil ID \'{perfil_id}\' is not an integer')
        return perfil_ids


class RequestPayload(BaseModel):
    titles: List[str] = Field(
        ...,
        title='Role titles',
        description='Role titles to be normalized.',
        min_items=1,
        max_items=1000,
        example=['recepcionista'],
    )
    origin: str = Field(
        default=None,
        title='Request origin',
        description='Used to identify the request source. Optional. Any string.',
        example='user_cv_form',
    )


class NormalizedRoleTitle(BaseModel):
    normalized_role: str = Field(
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
    seniority: List[str] = Field(
        ...,
        title='Seniorities',
        description='List of seniorities found in received role title.',
        example=[],
    )
    hierarchy: List[str] = Field(
        ...,
        title='Hierarchies',
        description='List of hierarchies found in received role title.',
        example=[],
    )
    areap_ids: List[int] = Field(
        ...,
        title='Area IDs',
        description='List of area IDs associated with this role ID. Filtered by perfil_ids query'
            ' parameter, if used.',
        example=[47, 73],
    )
    nivelh_ids: List[int] = Field(
        ...,
        title='Hierarchy IDs',
        description='List of hierarchy IDs associated with this role ID. Filtered by perfil_ids'
            ' query parameter, if used.',
        example=[4, 5],
    )
    perfil_ids: List[int] = Field(
        default=None,
        title='Profile IDs',
        description='List of matching profile IDs associated with this role ID. Only returned if'
            ' perfil_ids query parameter is used.',
        example=[1],
    )
    match_type: str = Field(
        default=None,
        title='Match type',
        description='Normalization match type. Either "database" or "ahocorasick". Only returned if'
            ' match_type query parameter is used.',
        example='database',
    )


class ResponsePayload(BaseModel):
    __root__: Dict[str, List[NormalizedRoleTitle]] = Field(
        ...,
        title='Normalized role titles',
        description='Role titles that could be normalized.',
        example={
            'recepcionista': [
                {
                    'normalized_role': 'Recepcionista',
                    'role_id': 1104,
                    'seniority': [],
                    'hierarchy': [],
                    'areap_ids': [
                        47,
                        73
                    ],
                    'nivelh_ids': [
                        4,
                        5
                    ],
                    "perfil_ids": [
                        1
                    ],
                    'match_type': 'database'
                }
            ]
        },
    )


class RoleNormalization:

    """
    Handles Role Normalization requests.
    """

    # Create a role normalizer
    role_normalizer = RoleMatcher()

    # Separators used to split received titles with multiple roles
    title_separators = [re.escape(separator) for separator in ['/', ',', ' ou ', ';', '|']]

    @spec.validate(
        json=RequestPayload,
        query=RequestParams,
        resp=Response(HTTP_200=ResponsePayload, HTTP_403=None),
        tags=['role-normalization']
    )
    def on_post(self, req, resp):
        """
        Normalizes received role titles - associates them to database role IDs, if possible.
        """
        self.normalize_roles(req, resp)

    def normalize_roles(self, req, resp):

        request_payload = req.context.get('json')
        role_titles = request_payload.titles
        request_params = req.context.get('query')
        include_match_type = request_params.match_type == True
        perfil_ids_filter = request_params.perfil_ids
        resp_obj = OrderedDict()

        # For each received title
        for role_title in role_titles:
            norm_roles = []
            # Split title into single roles
            for role in re.split('|'.join(self.title_separators), role_title):
                # Normalize title and check if it matches a database role title
                logger.info(f'Received role: {role}')
                norm_title, norm_role, match_type = self.role_normalizer.normalize_and_match(
                    role,
                    perfil_ids_filter
                )
                logger.info(f'Processed role: {norm_title}')
                # If so, add it to the list of normalized roles for the current title
                if norm_role is not None:
                    logger.info(f'Normalized role ID: {norm_role.role_id}')
                    logger.info(f'Normalized role title: {norm_role.title}')
                    norm_role_resp = {
                        'normalized_role': norm_role.title,
                        'role_id': norm_role.role_id,
                        'seniority': norm_role.seniorities,
                        'hierarchy': norm_role.hierarchies,
                        'areap_ids': norm_role.areap_ids,
                        'nivelh_ids': norm_role.nivelh_ids
                    }
                    if include_match_type:
                        norm_role_resp['match_type'] = match_type
                    if perfil_ids_filter:
                        norm_role_resp['perfil_ids'] = norm_role.perfil_ids
                    norm_roles.append(norm_role_resp)

            # Add current title normalized roles to the response object
            if norm_roles:
                resp_obj[role_title] = norm_roles

        # Return 200 if one or more roles were normalized
        if resp_obj:
            resp.status = falcon.HTTP_200
        # 204 otherwise
        else:
            resp.status = falcon.HTTP_204

        resp.media = resp_obj
