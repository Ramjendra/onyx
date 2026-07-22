# Blackstone AgentiAI Insider Risk Demo

This workspace contains a lightweight browser-based demo for presenting an insider-trading prevention concept to a client.

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

## Demo narrative
1. AgentiAI ingests employee email, chat, and collaboration messages.
2. The system scores each message for policy risk using context and known red flags.
3. Compliance receives an alert with evidence and recommended actions.

This is designed for presentation purposes and can be expanded into a real integration with Microsoft 365, Google Workspace, Slack, Teams, or email archives.
