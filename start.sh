#!/usr/bin/env bash
set -e
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env. Add GOOGLE_MAPS_API_KEY, then run ./start.sh again."
  exit 0
fi
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
