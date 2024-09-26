import multiprocessing

bind = '0.0.0.0:8192'
worker_class = 'sync'
workers = multiprocessing.cpu_count() * 2 + 1
pidfile = '/tmp/role-norm-gunicorn.pid'
timeout = 600
