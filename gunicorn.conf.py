"""
Gunicorn production configuration.

WORKER MATH:
  workers = 2 × CPU_cores + 1  →  on a 4-core server = 9 workers
  Each gevent worker handles hundreds of concurrent connections using
  cooperative multitasking (greenlets) instead of blocking OS threads.

  With 9 gevent workers, the server can comfortably handle 300+ simultaneous
  users — each worker serves many requests concurrently while waiting on DB/IO.

HOW TO USE:
  gunicorn -c gunicorn.conf.py ehr_project.wsgi:application
"""
import multiprocessing

# Number of worker processes
# On Render free tier (1 CPU): workers=3
# On a 4-core VPS: workers=9
workers = multiprocessing.cpu_count() * 2 + 1

# gevent workers handle concurrent connections without blocking
# Each worker can serve hundreds of requests "at the same time" by
# switching between them while waiting for DB/API responses
worker_class = 'gevent'
worker_connections = 1000  # max concurrent connections per worker

# Bind
bind = '0.0.0.0:8000'

# Timeouts
timeout = 120          # kill worker if it doesn't respond in 120s
keepalive = 5          # keep connections alive for 5s (reduces TCP overhead)
graceful_timeout = 30  # give workers 30s to finish requests on restart

# Logging
accesslog = '-'   # stdout
errorlog  = '-'   # stderr
loglevel  = 'info'

# Restart workers after 1000 requests to prevent memory leaks
max_requests = 1000
max_requests_jitter = 100  # randomise so all workers don't restart at once
