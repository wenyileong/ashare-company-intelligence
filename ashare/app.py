"""Single entry point for the packaged application.

* No arguments  -> desktop interface.
* Any arguments -> command line (identical to ``python -m ashare.cli``).
"""
import io
import sys


def main():
    # A windowed (no-console) executable has no stdout/stderr; give the
    # libraries somewhere harmless to write.
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    # Windows pipes and redirected output default to the ANSI code page,
    # which cannot encode Chinese; force UTF-8 and never fail on output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) > 1:
        import os
        from .cli import app
        try:
            app()
        except SystemExit:
            raise
        except Exception as exc:  # concise message instead of a traceback
            if os.getenv("ASHARE_DEBUG"):
                raise
            from .errors import friendly_error
            print(friendly_error(exc), file=sys.stderr)
            print("Set ASHARE_DEBUG=1 for the full traceback.", file=sys.stderr)
            sys.exit(1)
    else:
        from .gui import run
        run()


if __name__ == "__main__":
    main()
