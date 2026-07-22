#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f .deploy.pid ]]; then
  echo "No .deploy.pid found. Is the app running?"
  exit 1
fi

PID=$(cat .deploy.pid)
if [[ -z "$PID" ]]; then
  echo "PID file is empty. Removing .deploy.pid."
  rm -f .deploy.pid
  exit 1
fi

if kill -0 "$PID" >/dev/null 2>&1; then
  echo "Stopping app process $PID"
  kill "$PID"
  sleep 1
  if kill -0 "$PID" >/dev/null 2>&1; then
    echo "Process did not stop, sending SIGKILL"
    kill -9 "$PID" || true
  fi
  echo "Stopped."
else
  echo "Process $PID is not running."
fi

rm -f .deploy.pid

echo "Cleanup complete."
