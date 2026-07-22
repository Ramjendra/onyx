#!/usr/bin/env bash
set -euo pipefail

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LOCAL_DIR"

echo "Deploying Onyx locally in $LOCAL_DIR"

PYTHON_CMD=python3
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  PYTHON_CMD=python
fi

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "ERROR: Python is not installed or not on PATH."
  exit 1
fi

"$PYTHON_CMD" -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [[ -f .deploy.pid ]]; then
  PID=$(cat .deploy.pid)
  if kill -0 "$PID" >/dev/null 2>&1; then
    echo "Stopping previous app process $PID"
    kill "$PID" || true
  fi
fi

nohup .venv/bin/python app.py > app.log 2>&1 &
echo "$!" > .deploy.pid

echo "Deployment complete. App started with PID $(cat .deploy.pid)."
echo "Open http://localhost:5000/"
