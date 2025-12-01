"""Gunicorn configuration for production deployment."""
import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.getenv('SERVER_PORT', '8081')}"
backlog = 2048

# Worker processes
workers = int(os.getenv('WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'uvicorn.workers.UvicornWorker'
# Maximum concurrent connections per worker (increased for high throughput)
# Each connection can handle multiple async requests
worker_connections = 2048
max_requests = 10000  # Increase to reduce worker recycling overhead
max_requests_jitter = 500
timeout = 120
keepalive = 30  # Increased keepalive for better connection reuse

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('LOG_LEVEL', 'info').lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'sticker-processor'

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = None
# certfile = None

# Worker lifecycle hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Gunicorn master process starting")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info(f"Gunicorn server ready. Workers: {workers}")

def on_reload(server):
    """Called to recycle workers during a reload."""
    server.log.info("Gunicorn reloading")

def worker_int(worker):
    """Called when a worker receives a SIGINT or SIGQUIT signal."""
    worker.log.info(f"Worker {worker.pid} received interrupt signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forked child, re-executing")

def worker_abort(worker):
    """Called when a worker times out."""
    worker.log.info(f"Worker {worker.pid} timed out and will be restarted")

