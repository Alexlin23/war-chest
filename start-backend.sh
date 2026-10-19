#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
export WARCHEST_DEV=1
exec python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000 --reload
