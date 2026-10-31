"""Plain-language explanations of common failures (v2.0.1)."""
from __future__ import annotations


def friendly_error(exc: BaseException) -> str:
    """One or two lines saying what failed and what to do next (v2.1: in the desktop's language)."""
    from .i18n import tr
    try:
        import httpx
    except ImportError:                      # pragma: no cover
        httpx = None
    base = f"Error: {type(exc).__name__}: {exc}"
    if httpx is not None and isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        url = str(exc.request.url)
        if code in (404, 410):
            hint = tr("error.moved", "The source no longer serves this address; it has probably moved. Run Check > "
                                     "Self-test (ashare-cli self-test) to see which source changed, and send "
                                     "selftest_report.json with a bug report.")
        elif code in (403, 429):
            hint = tr("error.refused", "The source refused or rate-limited the request. Wait a while before trying "
                                       "again; the program never works around such limits.")
        elif code >= 500:
            hint = tr("error.server", "The source had a server error. Try again later.")
        else:
            hint = tr("error.changed", "Run Check > Self-test to see whether the source has changed.")
        return f"Error: HTTP {code} from {url}\n{hint}"
    if httpx is not None and isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ProxyError)):
        return base + "\n" + tr("error.unreachable", "This computer could not reach the source. Check the network "
                                                    "connection, proxy or firewall, then run Check > Self-test.")
    if httpx is not None and isinstance(exc, httpx.TimeoutException):
        return base + "\n" + tr("error.timeout", "The source did not answer in time. Try again later.")
    return base


def write_error_file(exc: BaseException, argv: list[str] | None = None) -> str | None:
    """v2.1 (finding 96): the full error, with its traceback, in ``logs/error_<time>.txt``; returns the path.
    A failure can then be diagnosed from the file, where the screen shows only a one-line message."""
    import os
    import traceback
    from datetime import datetime
    from pathlib import Path
    try:
        folder = Path(os.getenv("ASHARE_LOG_DIR", "logs"))
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = folder / f"error_{stamp}.txt"
        from . import __version__
        head = f"ashare {__version__}\ncommand: {' '.join(argv or [])}\n\n"
        path.write_text(head + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                        encoding="utf-8")
        return str(path)
    except Exception:
        return None
