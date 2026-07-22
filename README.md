# Onyx Insider Risk Demo

This workspace contains the Onyx insider risk demo: a browser-based UI backed by a Flask API for mock communication monitoring and department triage.

## What it shows
- AI-assisted monitoring of employee communications
- Detection of risky patterns such as external recipients, sensitive words, and unusual timing
- A compliance workflow that escalates to legal and investigation teams

## How to run it
Start the Python backend:

```bash
cd /home/ramram/Desktop/Personal/Onyx
/home/ramram/Desktop/Personal/Onyx/.venv/bin/python app.py
```

Then open http://localhost:5000/ in your browser.

## Deploying to a remote server
A deployment script is included at `deploy.sh`.

Example usage:
```bash
cd /home/ramram/Desktop/Personal/Onyx
REMOTE_USER=ubuntu REMOTE_HOST=server.example.com REMOTE_PATH=/var/www/onyx ./deploy.sh
```

If you need the app to restart automatically, set `REMOTE_RESTART_CMD`:
```bash
REMOTE_USER=ubuntu REMOTE_HOST=server.example.com REMOTE_PATH=/var/www/onyx REMOTE_RESTART_CMD="cd /var/www/onyx && ./restart.sh" ./deploy.sh
```

The script will:
- sync project files to the remote host with `rsync`
- create or update a Python virtual environment at the target path
- install dependencies from `requirements.txt`
- optionally run the restart command if provided

## Demo narrative
1. AgentiAI ingests employee email, chat, and collaboration messages.
2. The system scores each message for policy risk using context and known red flags.
3. Compliance receives an alert with evidence and recommended actions.

This is designed for presentation purposes and can be expanded into a real integration with Microsoft 365, Google Workspace, Slack, Teams, or email archives.
