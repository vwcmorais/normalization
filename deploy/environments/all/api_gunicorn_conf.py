import multiprocessing

bind = '0.0.0.0:8192'
worker_class = 'sync'
workers = multiprocessing.cpu_count()
pidfile = '/seek/role-norm-gunicorn.pid'
timeout = 450
