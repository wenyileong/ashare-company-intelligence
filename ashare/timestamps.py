"""Trusted timestamps for manifests (v2.3.0, plan section B10): scaffold only.

The plan made this feature optional and off by default, and allowed it to wait for a later version if no suitable
library could be chosen. Building and verifying RFC 3161 requests and their signature chains needs a library that
has not yet been reviewed for this program (its licence, its maintenance and what it pulls in), so in v2.3.0 the
switch ``timestamps`` exists but the feature refuses to run. Release manifests keep their SHA-256 hashes and the
database fingerprint, as before.
"""
from __future__ import annotations


class NotAvailable(RuntimeError):
    pass


def timestamp_manifest(path) -> dict:
    from .features import require
    require("timestamps")
    raise NotAvailable("trusted timestamps are not available in v2.3.0: the library that builds and verifies "
                       "RFC 3161 tokens has not yet been chosen and reviewed (plan section B10)")
