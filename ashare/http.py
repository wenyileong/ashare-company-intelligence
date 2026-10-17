"""Rate-limited HTTP client.

v1.4 adds transport injection so adapters can be exercised offline against
``httpx.MockTransport`` (or a recorded-response transport) in tests and in
the self-test's dry-run mode. ``set_default_transport`` affects every client
created afterwards; pass ``transport=`` to override for one client.
"""
import threading
import time
import httpx
from .config import REQUEST_TIMEOUT

_DEFAULT_TRANSPORT = None

# v2.0.1: cooperative cancellation. The desktop Stop button sets the flag;
# the next network request (or PDF read) raises Cancelled. Cancelled derives
# from BaseException so that per-item ``except Exception`` handlers in the
# pipelines do not swallow it; everything committed before it stays saved.
_CANCEL = threading.Event()


class Cancelled(BaseException):
    """The user stopped the running action."""


def request_cancel() -> None:
    _CANCEL.set()


def reset_cancel() -> None:
    _CANCEL.clear()
    _READ.update(n=0, t0=None)


_READ = {"n": 0, "t0": None}


def document_heartbeat(path=None, every: int = 25) -> None:
    """v2.0.2: called for every document read; prints a progress line every
    ``every`` documents so long extractions show they are working, and lets
    the Stop button end them between documents."""
    check_cancel()
    _READ["n"] += 1
    if _READ["t0"] is None:
        _READ["t0"] = time.monotonic()
    if _READ["n"] % every == 0:
        import sys
        rate = _READ["n"] / max(time.monotonic() - _READ["t0"], 1e-6)
        sys.stdout.write(f"... {_READ['n']} documents read ({rate:.1f} per second)\n")
        try:
            sys.stdout.flush()
        except Exception:
            pass


def reset_heartbeat() -> None:
    _READ.update(n=0, t0=None)


def check_cancel() -> None:
    if _CANCEL.is_set():
        raise Cancelled("stopped by the user; everything saved so far is kept, and running it again resumes")


def set_default_transport(transport) -> None:
    """Install (or with ``None`` remove) a transport used by new clients."""
    global _DEFAULT_TRANSPORT
    _DEFAULT_TRANSPORT = transport


def default_transport():
    return _DEFAULT_TRANSPORT


class RateLimitedClient:
    def __init__(self, user_agent: str, requests_per_second: float = 1.0, transport=None,
                 retries: int = 3):
        self.delay = 1.0 / max(requests_per_second, 0.1)
        self.last_request = 0.0
        self.retries = max(1, retries)
        transport = transport if transport is not None else _DEFAULT_TRANSPORT
        kwargs = {"transport": transport} if transport is not None else {}
        if transport is not None:
            # Offline transports need no pacing or backoff.
            self.delay = 0.0
        self.client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )
        self.offline = transport is not None

    def _pace(self):
        check_cancel()
        elapsed = time.monotonic() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _request(self, method: str, url: str, **kwargs):
        last_error = None
        for attempt in range(self.retries):
            try:
                self._pace()
                response = self.client.request(method, url, **kwargs)
                self.last_request = time.monotonic()
                response.raise_for_status()
                return response
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                if attempt == self.retries - 1:
                    raise
                if not self.offline:
                    time.sleep(min(2 ** attempt, 8))
        raise last_error

    def get(self, url: str, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._request("POST", url, **kwargs)

    def close(self):
        self.client.close()
