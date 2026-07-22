#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-}"
REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_PATH="${REMOTE_PATH:-/var/www/onyx}"
SSH_KEY_PATH="${SSH_KEY_PATH:-}"
SSH_PORT="${SSH_PORT:-22}"
REMOTE_RESTART_CMD="${REMOTE_RESTART_CMD:-}"

if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "ERROR: Please set REMOTE_USER and REMOTE_HOST before running this script."
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

if [[ -n "$REMOTE_RESTART_CMD" ]]; then
  echo "Running remote restart command: $REMOTE_RESTART_CMD"
  ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" bash -lc "'
set -euo pipefail
cd \"$REMOTE_PATH\"
$REMOTE_RESTART_CMD
'
"
else
  echo "No remote restart command provided. If you want the app to restart automatically, set REMOTE_RESTART_CMD before running deploy.sh."
fi

echo "Deployment complete."
