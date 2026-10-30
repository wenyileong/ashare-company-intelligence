"""A parse function for the parallel tests, importable by spawned workers."""
import time


def slow_job(job, reader):
    time.sleep(job.get("delay", 0))
    return job["id"]
