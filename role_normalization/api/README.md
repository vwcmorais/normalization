# Role Normalization API

The Role Normalization API uses a bare-bones configuration of [Falcon](https://falconframework.org/) web framework and is served using [Gunicorn](https://gunicorn.org/).

Falcon code is quite simple. Endpoint `/v1/role_normalization/catho` is associated with the `RoleNormalization` class and is handled by the `on_post()` method. Any role normalization code should be placed there or be called from there.

Gunicorn settings are stored in the `gunicorn_conf.py` file. It should work as is but you may need to edit some settings depending on your environment, like `bind` that defines the address and port that Gunicorn will use.

Requests are authenticated using Basic authentication. Valid username and password are stored in AWS Secrets Manager.

Sample request - fill authorization header before running it:

```shell
curl \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Basic ...' \
  -d '{"titles": ["Cientista de Dados Sênior Líder", "Analista de Bancos de Dados Junior", "Recepcionista/Secretária"]}' \
  'http://localhost:8192/v1/role_normalization/catho'
```

## Development Environment

The API can be run locally for development and debugging. Python packages will be installed on a virtual environment so they won't affect your local setup. In this environment the API will automatically reload whenever it's code is edited and it will print requests received and debug messages to stdout/stderr. Note that you will need valid AWS credentials configured and loaded in your terminal for the API to work - it needs to access AWS Secrets Manager. You also need to be connected to Catho's VPN in order to access Catho's databases.

```shell
sudo apt install libre2-dev
cd catho-role-normalization/
python3 -m virtualenv --python=python3 venv
source venv/bin/activate
pip3 install -r requirements.txt
mkdir venv/nltk_data/
python3 -c 'import nltk; nltk.download("stopwords"); nltk.download("rslp"); nltk.download("mac_morpho"); nltk.download("words")'
role_normalization/api/dev_env_start.sh
```

To run unit tests:

```shell
cd catho-role-normalization/
source venv/bin/activate
pytest --verbose --capture=tee-sys .
```

## Production Environemnt

NGINX should proxy requests to Gunicorn. The address and port Gunicorn will use can be set through the `bind` option in the `gunicorn_conf.py` file. Also, `PYTHONPATH` must include the location of `role_normalization` module for the API to work.

Example `gunicorn.sh` script, considering that repository files are available at `/seek/role-normalization/`:

```shell
export PYTHONPATH="/seek/role-normalization:$PYTHONPATH"
cd /seek/role-normalization/role_normalization/api/
gunicorn --config ./gunicorn_conf.py api:app
```
