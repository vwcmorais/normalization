import multiprocessing

bind = '0.0.0.0:8192'
worker_class = 'sync'
workers = multiprocessing.cpu_count() * 2
pidfile = '/seek/role-norm-gunicorn-events.pid'
timeout = 450
