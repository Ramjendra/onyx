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

create_venv() {
  "$PYTHON_CMD" -m venv .venv
}

if ! create_venv >/dev/null 2>&1; then
  echo "Local venv creation failed. Trying to install python3-venv on Debian/Ubuntu..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3-venv
    if ! create_venv >/dev/null 2>&1; then
      echo "ERROR: Failed to create virtual environment after installing python3-venv."
      exit 1
    fi
  else
    echo "ERROR: venv creation failed and apt-get is not available to install python3-venv."
    echo "Install the system package manually and retry."
    exit 1
  fi
fi

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
