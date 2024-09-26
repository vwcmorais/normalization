import falcon
import basicauth
import os

from role_normalization import settings
from role_normalization.api.role_norm_events import JobRoleNormalizer, UserRoleNormalizer


spec = settings.spec


class AuthMiddleware:

    auth_user = settings.role_norm_api_user()
    auth_password = settings.role_norm_api_password()

    def process_request(self, req, resp):

        if req.relative_uri == '/healthcheck' or \
                req.relative_uri == '/buildinfo' or \
                req.relative_uri.startswith('/v1/role_normalization/catho/doc/'):
            return

        auth = req.get_header('Authorization')

        if not auth:
            raise falcon.HTTPUnauthorized(
                title='Unauthorized',
                description='Missing authorization header')

        if not self._auth_is_valid(auth):
            raise falcon.HTTPUnauthorized(
                title='Unauthorized',
                description='Invalid authorization header')

    def _auth_is_valid(self, auth):
        try:

            username, password = basicauth.decode(auth)
            if username == self.auth_user and password == self.auth_password:
                return True

        except:
            pass

        return False


class RequireJSON:

    def process_request(self, req, resp):
        if not req.client_accepts_json:
            raise falcon.HTTPNotAcceptable(
                description='Responses encoded as JSON not accepted by client')

        if req.method in ('POST', 'PUT'):
            if 'application/json' not in req.content_type:
                raise falcon.HTTPUnsupportedMediaType(
                    title='Request not encoded as JSON')


class HealthCheck:

    @spec.validate(tags=['meta'])
    def on_get(self, req, resp):
        """
        Health check endpoint, used to check if the API is running and can be reached.
        """
        resp.text = '{"status": "OK", "description": "Role Normalization API available"}'
        resp.status = falcon.HTTP_200


class BuildInfo:

    @spec.validate(tags=['meta'])
    def on_get(self, req, resp):
        """
        API info endpoint - returns build version, Git commit ID, etc.
        """
        infopath = '/seek/build_info.json'
        if os.path.isfile(infopath) and os.access(infopath, os.R_OK):
            try:
                file = open(infopath)
                resp.text = file.read()
                file.close()
            except:
                resp.text = '{"status": "ERROR", "description": "Error reading build_info.json file"}'
                resp.status = falcon.HTTP_500
            else:
                resp.status = falcon.HTTP_200
        else:
            resp.text = '{"status": "Unknown", "description": "build_info.json file unavailable"}'
            resp.status = falcon.HTTP_200


app = falcon.App(middleware=[
    AuthMiddleware(),
    RequireJSON()
])
app.req_options.strip_url_path_trailing_slash = True

app.add_route('/healthcheck', HealthCheck())
app.add_route('/buildinfo', BuildInfo())
app.add_route('/v1/role_normalization/events/jobs', JobRoleNormalizer())
app.add_route('/v1/role_normalization/events/users', UserRoleNormalizer())

spec.register(app)
