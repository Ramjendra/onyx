# Onyx Insider Risk Demo

This workspace contains the Onyx insider risk demo: a browser-based UI backed by a Flask API for mock communication monitoring and department triage.

## What it shows
- AI-assisted monitoring of employee communications
- Detection of risky patterns such as external recipients, sensitive words, and unusual timing
- A compliance workflow that escalates to legal and investigation teams
- **SLM-powered predictive scoring** via Ollama (with automatic fallback)

## One-Command Setup

Run the deployment script — it handles **everything** in a single stage:

```bash
cd /home/ramram/Desktop/Personal/Onyx
./deploy.sh
```

The script will automatically:
1. Create/update a Python virtual environment in `.venv`
2. Install Python dependencies from `requirements.txt`
3. **Install Ollama** if not already present
4. **Start the Ollama service** and **pull the `llama3.1` model**
5. Start the Onyx app and write its PID to `.deploy.pid`

After deployment, open: **http://localhost:5000/**

### Environment Variables (optional)

| Variable | Default | Description |
|---|---|---|
| `MODEL_NAME` | `llama3.1:latest` | Ollama model to use for scoring |
| `MODEL_ENDPOINT` | `http://127.0.0.1:11434/api/generate` | SLM API endpoint |
| `MODEL_TIMEOUT` | `60` | Request timeout in seconds |

Example with a custom model:
```bash
MODEL_NAME=gemma2:2b ./deploy.sh
```

## Manual Start (without deploy script)

```bash
cd /home/ramram/Desktop/Personal/Onyx
ollama serve &          # Start Ollama in background
ollama pull llama3.1    # Pull the model (first time only)
.venv/bin/python app.py # Start the app
```

Then open http://localhost:5000/

## Stopping the App

```bash
./stop.sh
```

## SLM Scoring Architecture

The system uses a 3-tier scoring strategy:

1. **Ollama (default)** — Calls local `llama3.1` for AI-driven risk scoring
2. **Custom endpoint** — Set `MODEL_ENDPOINT` to use an external SLM service
3. **Fallback demo model** — Deterministic weighted linear model if SLM is unavailable

The dashboard shows a live SLM connection status indicator in the header.

## Demo narrative
1. AgentiAI ingests employee email, chat, and collaboration messages.
2. The system scores each message for policy risk using the SLM and feature vectors.
3. Compliance receives an alert with evidence and recommended actions.

This is designed for presentation purposes and can be expanded into a real integration with Microsoft 365, Google Workspace, Slack, Teams, or email archives.
