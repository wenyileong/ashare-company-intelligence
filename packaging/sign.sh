#!/usr/bin/env bash
# Code-signing hook for builds made on Linux (v2.0), using osslsigncode.
# Signs only when a certificate is configured; otherwise prints a note.
#   ASHARE_SIGN_CERT=/path/cert.pfx  ASHARE_SIGN_PASSWORD=...  packaging/sign.sh FILE.exe
set -euo pipefail
f="${1:?usage: sign.sh FILE}"
if [ -z "${ASHARE_SIGN_CERT:-}" ]; then
  echo "Not signed: $(basename "$f") (set ASHARE_SIGN_CERT to sign)"
  exit 0
fi
ts="${ASHARE_SIGN_TIMESTAMP:-http://timestamp.digicert.com}"
osslsigncode sign -pkcs12 "$ASHARE_SIGN_CERT" ${ASHARE_SIGN_PASSWORD:+-pass "$ASHARE_SIGN_PASSWORD"} \
  -h sha256 -t "$ts" -n "A-share Company Intelligence" -in "$f" -out "$f.signed"
mv "$f.signed" "$f"
osslsigncode verify "$f" >/dev/null && echo "Signed $(basename "$f")"
