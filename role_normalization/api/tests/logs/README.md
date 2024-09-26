# Role Normalization API Coverage Test

To test changes made to the Role Normalization API, it can be useful to check how it compares to the API
currently running in production. To do that:

1. Download production API logs using the `get_role_norm_logs.ipynb` notebook
2. Run the Role Normalization API locally
3. Run the `replay_log_requests.py` script as shown below

```shell
python3 role_normalization/api/tests/logs/replay_log_requests.py \
    -l role_norm_logs.2024-02-11.2024-02-17.csv \
    -a 'localApiBase64Auth='
```

This script will send the requests found in the production API log to the local API and print a
comparison between the two API versions. This report will include:

- Non-normalized matches: roles that failed to be normalized both in production and locally
- Normalized matches: roles that were normalized to the same role ID in production and locally
- Differences: roles that were normalized to different role IDs in production and locally
- Regressions: roles that were successfully normalized in production but failed to be normalized locally
- Improvements: roles that failed to be normalized in production but were successfully normalized locally

Ideally, changes should have a high rate of Improvements and a low rate of Regressions. Differences
should be checked but they are not necessarily a problem - role titles being normalized to a more
specific role ID, for example ("DBA Sênior" locally and just "DBA" in production).
