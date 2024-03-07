#!/usr/bin/env sh

# Sets up API server
# Expects access to Python environment with the requirements 
# for this project installed.
set -e

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-7481}"
API_APP_DIR="${API_APP_DIR:-$PWD}"
API_ASGI_APP="${API_ASGI_APP:-leaderboard.api.api:run_app}"
API_UVICORN_WORKERS="${API_UVICORN_WORKERS:-2}"

uvicorn --reload \
  --port "$API_PORT" \
  --host "$API_HOST" \
  --app-dir "$API_APP_DIR" \
  --workers "$API_UVICORN_WORKERS" \
  "$API_ASGI_APP"
