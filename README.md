# Role Normalization Routines

Routines to normalize user and job roles. For non-normalized user roles (CV and past work experience roles), find the corresponding role ID using the Role Normalization API and save it in Catho's databases. Same for job non-normalized roles.

This routine should be run regularly to ensure database roles are normalized. Most of our recommendation and scoring algorithms rely on this data.

## Development Environment

The Role Normalization Routine can be run locally for development and debugging. Python packages will be installed on a virtual environment so they won't affect system packages. Note that you will need valid AWS credentials configured and loaded in your terminal for the API to work - it needs to access AWS Secrets Manager. You also need to be connected to Catho's VPN in order to access Catho's databases.

If you are running the Role Normalization API locally as well, you have probably already created Python's virtual environment. Skip unecessary commands below.

```shell
cd catho-role-normalization/
python3 -m virtualenv --python=python3 venv
source venv/bin/activate
pip3 install -r requirements.txt
mkdir venv/nltk_data/
python3 -c 'import nltk; nltk.download("stopwords"); nltk.download("rslp"); nltk.download("mac_morpho"); nltk.download("words")'
ROLE_NORM_REPO_DIR="$(pwd)"
LOG_LEVEL="DEBUG" PYTHONPATH="$ROLE_NORM_REPO_DIR:$PYTHONPATH" python3 role_normalization/routine/users_role_norm.py
LOG_LEVEL="DEBUG" PYTHONPATH="$ROLE_NORM_REPO_DIR:$PYTHONPATH" python3 role_normalization/routine/jobs_role_norm.py
```

To see command line options available:

```shell
PYTHONPATH="$ROLE_NORM_REPO_DIR:$PYTHONPATH" python3 role_normalization/routine/users_role_norm.py --help
PYTHONPATH="$ROLE_NORM_REPO_DIR:$PYTHONPATH" python3 role_normalization/routine/jobs_role_norm.py --help
```

## Production Environment

Set `PYTHONPATH` to include the `role_normalization` module and run `users_role_norm.py` and/or `jobs_role_norm.py`.

Example `users_role_norm.sh` script, considering that repository files are available at `/seek/role-normalization/`:

```shell
export PYTHONPATH="/seek/role-normalization:$PYTHONPATH"
python3 /seek/role-normalization/role_normalization/routine/users_role_norm.py
```
