#!/usr/bin/env bash
# Build on macOS or Linux (produces a native binary for that OS only).
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .build-venv
. .build-venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-dev.txt
python -m pytest -q
pyinstaller --noconfirm --clean packaging/ashare.spec --distpath dist --workpath build
dist/AShareScraper/ashare-cli version
python packaging/build_docs.py dist/AShareScraper/docs
echo "Built: dist/AShareScraper/"
