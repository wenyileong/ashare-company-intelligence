"""Plain-language explanations of common failures (v2.0.1)."""
from __future__ import annotations


def friendly_error(exc: BaseException) -> str:
    """One or two lines saying what failed and what to do next."""
    try:
        import httpx
    except ImportError:                      # pragma: no cover
        httpx = None
    base = f"Error: {type(exc).__name__}: {exc}"
    if httpx is not None and isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        url = str(exc.request.url)
        if code in (404, 410):
            hint = ("The source no longer serves this address; it has probably moved. "
                    "Run Check > Self-test (ashare-cli self-test) to see which source changed, "
                    "and send selftest_report.json with a bug report.")
        elif code in (403, 429):
            hint = ("The source refused or rate-limited the request. Wait a while before trying again; "
                    "the program never works around such limits.")
        elif code >= 500:
            hint = "The source had a server error. Try again later."
        else:
            hint = "Run Check > Self-test to see whether the source has changed."
        return f"Error: HTTP {code} from {url}\n{hint}"
    if httpx is not None and isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ProxyError)):
        return (f"{base}\nThis computer could not reach the source. Check the network connection, proxy or "
                "firewall, then run Check > Self-test.")
    if httpx is not None and isinstance(exc, httpx.TimeoutException):
        return f"{base}\nThe source did not answer in time. Try again later."
    return base
