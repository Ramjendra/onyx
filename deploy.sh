#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-}"
REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_PATH="${REMOTE_PATH:-}"
SSH_KEY_PATH="${SSH_KEY_PATH:-}"
SSH_PORT="${SSH_PORT:-22}"
REMOTE_RESTART_CMD="${REMOTE_RESTART_CMD:-}"

if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" || -z "$REMOTE_PATH" ]]; then
  echo "ERROR: Please set REMOTE_USER, REMOTE_HOST, and REMOTE_PATH before running this script."
  echo "Example: REMOTE_USER=ubuntu REMOTE_HOST=example.com REMOTE_PATH=/var/www/onyx ./deploy.sh"
  exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -p "$SSH_PORT")
if [[ -n "$SSH_KEY_PATH" ]]; then
  SSH_OPTS+=( -i "$SSH_KEY_PATH" )
fi

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_TARGET="${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}"

echo "Deploying Onyx to ${REMOTE_TARGET}"

rsync -avz --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.pyo' \
  --exclude 'tests' \
  "$LOCAL_DIR/" "$REMOTE_TARGET/"

ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" bash -lc "'
set -euo pipefail
mkdir -p \"$REMOTE_PATH\"
cd \"$REMOTE_PATH\"
PYTHON_CMD=python3
if ! command -v \"$PYTHON_CMD\" >/dev/null 2>&1; then
  PYTHON_CMD=python
fi
\"$PYTHON_CMD\" -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
'
"

if [[ -z "$REMOTE_RESTART_CMD" ]]; then
  echo "No REMOTE_RESTART_CMD provided; using default restart logic."
  REMOTE_RESTART_CMD="if [[ -f .deploy.pid ]]; then kill \$(cat .deploy.pid) || true; fi && nohup .venv/bin/python app.py > app.log 2>&1 & echo \"\$!\" > .deploy.pid"
else
  echo "Using provided restart command: $REMOTE_RESTART_CMD"
fi

ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" bash -lc "'
set -euo pipefail
cd \"$REMOTE_PATH\"
$REMOTE_RESTART_CMD
'
"

echo "Deployment complete."
