#!/usr/bin/env bash
set -euo pipefail

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LOCAL_DIR"

echo "========================================"
echo " Onyx Insider Risk Demo — Full Setup"
echo "========================================"

# ─── 1. Python Setup ───────────────────────────────────────────────────────────
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

echo ""
echo "[1/4] Setting up Python virtual environment..."
if ! create_venv >/dev/null 2>&1; then
  echo "  → venv creation failed. Trying to install python3-venv on Debian/Ubuntu..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
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
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✓ Python dependencies installed"

# ─── 2. Ollama Installation ───────────────────────────────────────────────────
echo ""
echo "[2/4] Checking Ollama installation..."

if command -v ollama >/dev/null 2>&1; then
  OLLAMA_VERSION=$(ollama --version 2>&1 | grep -oP '[\d.]+' | head -1)
  echo "  ✓ Ollama already installed (v${OLLAMA_VERSION})"
else
  echo "  → Ollama not found. Installing..."
  curl -fsSL https://ollama.ai/install.sh | sh
  if command -v ollama >/dev/null 2>&1; then
    echo "  ✓ Ollama installed successfully"
  else
    echo "  ⚠ Ollama installation failed. The app will use the fallback demo model."
    echo "  → You can install it manually later: https://ollama.ai"
  fi
fi

# ─── 3. Ollama Service & Model ────────────────────────────────────────────────
echo ""
echo "[3/4] Starting Ollama and pulling SLM model..."

MODEL_NAME="${MODEL_NAME:-llama3.1:latest}"

if command -v ollama >/dev/null 2>&1; then
  # Start Ollama service if not already running
  if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "  → Starting Ollama service..."
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    OLLAMA_PID=$!
    echo "  → Waiting for Ollama to become ready..."

    RETRIES=0
    MAX_RETRIES=15
    while ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do
      sleep 2
      RETRIES=$((RETRIES + 1))
      if [[ $RETRIES -ge $MAX_RETRIES ]]; then
        echo "  ⚠ Ollama did not start within 30s. Check /tmp/ollama.log"
        echo "  → The app will use the fallback demo model."
        break
      fi
    done
  fi

  if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "  ✓ Ollama service is running"

    # Check if the model is already pulled
    if curl -sf http://127.0.0.1:11434/api/tags | grep -q "\"${MODEL_NAME}\"" 2>/dev/null; then
      echo "  ✓ Model '${MODEL_NAME}' already available"
    else
      echo "  → Pulling model '${MODEL_NAME}' (this may take a few minutes on first run)..."
      ollama pull "$MODEL_NAME"
      if [[ $? -eq 0 ]]; then
        echo "  ✓ Model '${MODEL_NAME}' pulled successfully"
      else
        echo "  ⚠ Failed to pull model. The app will use the fallback demo model."
      fi
    fi
  fi
else
  echo "  ⚠ Ollama not available — skipping model setup"
  echo "  → The app will use the built-in fallback demo model for scoring."
fi

# ─── 4. Start the Onyx App ──────────────────────────────────────────────────
echo ""
echo "[4/4] Starting Onyx app..."

if [[ -f .deploy.pid ]]; then
  PID=$(cat .deploy.pid)
  if kill -0 "$PID" >/dev/null 2>&1; then
    echo "  → Stopping previous app process $PID"
    kill "$PID" || true
    sleep 1
  fi
fi

nohup .venv/bin/python app.py > app.log 2>&1 &
echo "$!" > .deploy.pid

echo ""
echo "========================================"
echo " ✅ Deployment complete!"
echo "========================================"
echo ""
echo "  App PID     : $(cat .deploy.pid)"
echo "  Dashboard   : http://localhost:5000/"
echo "  Model Status: http://localhost:5000/api/model-status"
echo ""

# Quick health check
sleep 2
if curl -sf http://localhost:5000/api/model-status >/dev/null 2>&1; then
  SLM_STATUS=$(curl -sf http://localhost:5000/api/model-status)
  AVAILABLE=$(echo "$SLM_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('available', False))" 2>/dev/null || echo "unknown")
  BACKEND=$(echo "$SLM_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('backend', 'unknown'))" 2>/dev/null || echo "unknown")
  if [[ "$AVAILABLE" == "True" ]]; then
    echo "  🟢 SLM Status : Connected (${BACKEND})"
  else
    echo "  🔴 SLM Status : Fallback mode (${BACKEND})"
  fi
else
  echo "  ⏳ App is starting up... check http://localhost:5000/ in a moment"
fi
echo ""
