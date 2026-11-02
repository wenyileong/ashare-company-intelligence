"""A parse function for the parallel tests, importable by spawned workers."""
import time


def slow_job(job, reader):
    time.sleep(job.get("delay", 0))
    return job["id"]


def heartbeat_job(job, reader):
    """v2.1.2 (finding 124): a worker of the desktop program has no console; 30 heartbeats must not fail."""
    import sys
    from ashare.http import document_heartbeat
    sys.stdout = None
    for _ in range(30):
        document_heartbeat()
    return 30
