from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from flask import Flask, jsonify, send_from_directory, request
import json
import logging
import os
import re
import time
import urllib.request
import urllib.parse

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('onyx')

app = Flask(__name__)


def _normalize_tags(record):
    tags = record.get('riskTags', [])
    if isinstance(tags, str):
        return [tags.lower()]
    return [str(tag).lower() for tag in tags]


def _extract_email_body(message):
    if message.is_multipart():
        parts = []
        for part in message.walk():
            if part.get_content_maintype() == 'text':
                content = part.get_content()
                if isinstance(content, str):
                    parts.append(content)
        return '\n'.join(parts).strip()
    return message.get_content().strip()


def _infer_risk_tags(text):
    text = text.lower()
    tags = []
    keyword_map = {
        'external recipient': 'external recipient',
        'external contact': 'external contact',
        'broker': 'broker',
        'trading': 'trading',
        'sensitive': 'sensitive',
        'restricted': 'restricted',
        'encrypted': 'encrypted',
        'insider': 'insider',
        'legal': 'legal',
        'finance': 'finance',
        'pricing': 'pricing',
        'customer pricing': 'customer pricing',
        'p&l': 'p&l',
        'm&a': 'm&a',
        'acquisition': 'acquisition',
        'deal': 'deal',
        'confidential': 'confidential',
        'personal': 'personal',
        'board prep': 'board prep',
        'earnings': 'earnings',
        'forwarded': 'forwarded',
        'download': 'download',
    }

    for phrase, tag in keyword_map.items():
        if phrase in text:
            tags.append(tag)

    return tags


def _parse_email_record(raw_bytes):
    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    sender = parseaddr(message.get('From', ''))[1] or message.get('From', '').strip()
    recipient = parseaddr(message.get('To', ''))[1] or message.get('To', '').strip()
    subject = message.get('Subject', '').strip()
    body = _extract_email_body(message)
    text = ' '.join([subject, body, sender, recipient])
    risk_tags = _infer_risk_tags(text)
    risk_level = 'high' if any(tag in {'sensitive', 'confidential', 'acquisition', 'deal', 'pricing'} for tag in risk_tags) else 'medium' if risk_tags else 'low'

    return {
        'source': 'email',
        'sender': sender,
        'recipient': recipient,
        'timestamp': message.get('Date', 'unknown'),
        'riskLevel': risk_level,
        'riskTags': risk_tags,
        'subject': subject,
        'message': body or subject,
        'body': body,
    }


def determine_department(record):
    tags = _normalize_tags(record)
    source = record.get('source', '').lower()
    recipient = record.get('recipient', '').lower()
    if 'legal' in tags or 'confidential legal' in tags or 'outside-legal' in recipient:
        return 'Legal'
    if 'finance' in tags or 'pricing' in tags or 'customer pricing' in ' '.join(tags) or 'p&l' in ' '.join(tags):
        return 'Finance'
    if 'm&a' in tags or 'acquisition' in tags or 'deal' in tags:
        return 'M&A'
    if 'external recipient' in tags or 'external contact' in tags or 'broker' in tags or 'trading' in tags:
        return 'Compliance'
    if 'sensitive' in tags or 'restricted' in tags or 'encrypted' in tags or 'insider' in tags:
        return 'Security'
    if source == 'slack' or source == 'teams':
        return 'Communications'
    return 'Compliance'


def build_feature_vector(record):
    tags = _normalize_tags(record)
    source = str(record.get('source', '')).lower()
    recipient = str(record.get('recipient', '')).lower()
    message = ' '.join([
        str(record.get('message', '')),
        str(record.get('body', '')),
        str(record.get('subject', '')),
        ' '.join(tags),
        source,
        recipient,
    ]).lower()

    return {
        'risk_level': str(record.get('riskLevel', 'low')).lower(),
        'source_email': 1 if source == 'email' else 0,
        'source_slack': 1 if source == 'slack' else 0,
        'source_teams': 1 if source == 'teams' else 0,
        'external_recipient': 1 if 'external recipient' in tags or 'external contact' in tags else 0,
        'sensitive_content': 1 if 'sensitive' in tags or 'restricted' in tags or 'confidential' in tags else 0,
        'acquisition_context': 1 if 'm&a' in tags or 'acquisition' in tags or 'deal' in tags else 0,
        'price_context': 1 if 'pricing' in tags or 'customer pricing' in tags or 'p&l' in tags else 0,
        'personal_domain': 1 if 'personal' in recipient or '@gmail.com' in recipient or '@outlook.com' in recipient else 0,
        'message_length': len(message),
        'contains_forwarded': 1 if 'forwarded' in message else 0,
        'contains_download': 1 if 'download' in message else 0,
    }


SLM_SYSTEM_PROMPT = """You are a compliance risk scoring engine for an insider risk monitoring system.
You receive employee communication records and must assess the risk of policy violations.

You MUST respond with ONLY a valid JSON object (no markdown, no explanation outside JSON) with these exact keys:
- "score": integer 0-100 (0=no risk, 100=critical risk)
- "explanation": array of 2-4 short strings explaining the score
- "modelName": string, always "llama3.1"
- "modelVersion": string, always "8b-q4"

Scoring guidelines:
- 0-30: Routine communication, no policy flags
- 31-60: Minor concerns, warrants monitoring
- 61-80: Significant risk indicators present
- 81-100: Critical risk, immediate escalation recommended

Key risk factors to evaluate:
- External/personal recipients for sensitive data
- Non-public financial or M&A information
- Off-hours or unusual timing patterns
- Use of non-approved channels
- Bulk data access or downloads"""


def _extract_json_from_response(text):
    """Extract JSON from model response, handling markdown wrapping."""
    if not text or not text.strip():
        return None
    text = text.strip()
    md_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if md_match:
        text = md_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        obj_match = re.search(r'\{[\s\S]*\}', text)
        if obj_match:
            try:
                return json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                pass
    return None


def _validate_slm_output(parsed, model_name_fallback):
    """Normalize and validate parsed SLM output into a standard dict."""
    if not isinstance(parsed, dict):
        raise ValueError('SLM response is not a JSON object')

    score = parsed.get('score')
    if score is None:
        raise ValueError('SLM response missing score')
    score = int(score)
    score = max(0, min(100, score))

    explanation = parsed.get('explanation') or parsed.get('reason')
    if isinstance(explanation, str):
        explanation = [explanation]
    if not isinstance(explanation, list) or not explanation:
        explanation = ['SLM inference completed without detailed explanation.']

    return {
        'score': score,
        'explanation': explanation,
        'modelName': parsed.get('modelName') or model_name_fallback,
        'modelVersion': parsed.get('modelVersion') or 'ollama-local',
    }


def _call_ollama(record, feature_vector):
    """Call the local Ollama instance for risk scoring."""
    endpoint = os.getenv('MODEL_ENDPOINT', 'http://127.0.0.1:11434/api/generate')
    model_name = os.getenv('MODEL_NAME', 'llama3.1:latest')
    timeout = int(os.getenv('MODEL_TIMEOUT', '60'))

    prompt = (
        f'Analyze this employee communication record and produce a risk score.\n\n'
        f'Record:\n'
        f'  Source: {record.get("source", "unknown")}\n'
        f'  Sender: {record.get("sender", "unknown")}\n'
        f'  Recipient: {record.get("recipient", "unknown")}\n'
        f'  Timestamp: {record.get("timestamp", "unknown")}\n'
        f'  Message: {record.get("message", record.get("body", "N/A"))}\n\n'
        f'Respond with ONLY the JSON object.'
    )

    payload = json.dumps({
        'model': model_name,
        'system': SLM_SYSTEM_PROMPT,
        'prompt': prompt,
        'stream': False,
        'format': 'json',
    }).encode('utf-8')

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    elapsed = time.time() - start

    content = result.get('response', '{}')
    parsed = _extract_json_from_response(content) if isinstance(content, str) else content
    if parsed is None:
        raise ValueError(f'Could not parse Ollama response: {content[:200]}')

    output = _validate_slm_output(parsed, model_name)
    logger.info('Ollama SLM scored %d in %.1fs (model=%s)', output['score'], elapsed, model_name)
    return output


def _call_custom_endpoint(record, feature_vector, endpoint):
    """Call an external SLM HTTP endpoint with structured JSON payload."""
    timeout = int(os.getenv('MODEL_TIMEOUT', '30'))

    payload = json.dumps({
        'record': record,
        'featureVector': feature_vector,
    }).encode('utf-8')

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    elapsed = time.time() - start

    output = _validate_slm_output(result, os.getenv('MODEL_NAME', 'custom-slm'))
    logger.info('Custom SLM scored %d in %.1fs (endpoint=%s)', output['score'], elapsed, endpoint)
    return output


def _fallback_demo_model(record, feature_vector):
    score = 30
    explanation = []

    risk_level_weights = {
        'high': 18,
        'medium': 10,
        'low': 4,
    }
    risk_level = str(record.get('riskLevel', 'low')).lower()
    if risk_level in risk_level_weights:
        score += risk_level_weights[risk_level]
        explanation.append(f"Severity label '{risk_level}' contributed {risk_level_weights[risk_level]} points.")

    feature_weights = {
        'external_recipient': 16,
        'sensitive_content': 18,
        'acquisition_context': 14,
        'price_context': 12,
        'personal_domain': 10,
        'contains_forwarded': 8,
        'contains_download': 8,
        'source_slack': 4,
        'source_teams': 4,
    }

    for feature_name, weight in feature_weights.items():
        if feature_vector.get(feature_name, 0):
            score += weight
            explanation.append(f"Feature '{feature_name}' added {weight} points to the model score.")

    if feature_vector.get('message_length', 0) > 220:
        score += 4
        explanation.append('Longer message context added a modest signal lift.')

    if risk_level == 'high' and feature_vector.get('personal_domain'):
        score += 4
        explanation.append('High-severity handling to a personal destination amplified the scoring outcome.')

    explanation.append('A demo linear risk model handled the final predictive inference.')
    logger.info('Fallback demo model scored %d (SLM unavailable)', max(40, min(98, score)))
    return {
        'score': max(40, min(98, score)),
        'explanation': explanation,
        'modelName': 'demo-linear-risk-model',
        'modelVersion': 'v1.0.0',
    }


def score_with_model(record):
    feature_vector = build_feature_vector(record)
    endpoint = os.getenv('MODEL_ENDPOINT', '')

    try:
        if endpoint and '/api/generate' not in endpoint:
            model_output = _call_custom_endpoint(record, feature_vector, endpoint)
        else:
            model_output = _call_ollama(record, feature_vector)
    except Exception as exc:
        logger.warning('SLM call failed (%s), using fallback model', exc)
        model_output = _fallback_demo_model(record, feature_vector)

    return model_output['score'], model_output['explanation'], feature_vector, model_output['modelName'], model_output['modelVersion']


def calculate_predictive_score(record):
    score, explanation, _, _, _ = score_with_model(record)
    return score, explanation

alerts = [
    {
        "id": 1,
        "title": "External email about acquisition target",
        "severity": "high",
        "sender": "Maya Chen, VP Strategy",
        "recipient": "personal-email@domain.com",
        "timestamp": "08:43 ET",
        "score": 94,
        "summary": "A senior strategy lead forwarded a confidential note about an acquisition target to a personal account shortly before an internal board review.",
        "reasons": [
            "Contains sensitive terms related to a pending acquisition",
            "Recipient is outside approved corporate domains",
            "Timing aligns with a material board preparation event"
        ],
        "recommendedActions": [
            "Freeze the mailbox and preserve evidence",
            "Escalate to Legal, Compliance, and Security Operations",
            "Review trading activity for the employee and associated contacts"
        ],
        "department": "Legal",
        "evidence": [
            "Email subject: 'Confidential board prep – target valuation'",
            "The message included a detailed summary of deal structure",
            "The recipient domain is not sanctioned by policy"
        ]
    },
    {
        "id": 2,
        "title": "Late-night chat with a trading contact",
        "severity": "medium",
        "sender": "Daniel Ortiz, Portfolio Manager",
        "recipient": "external-trader@marketlink.com",
        "timestamp": "23:12 ET",
        "score": 82,
        "summary": "A portfolio manager discussed an unreleased earnings release and pricing assumptions in a direct message after normal business hours.",
        "reasons": [
            "Mentions unreleased earnings guidance",
            "Repeated contact with an external market participant",
            "Behavior deviates from normal business hours"
        ],
        "recommendedActions": [
            "Open a review case for potential information leakage",
            "Request chat log export and device review",
            "Monitor for suspicious trading patterns in the following 48 hours"
        ],
        "department": "Compliance",
        "evidence": [
            "The chat included phrases such as 'keep this under wraps'",
            "The contact appears on a restricted watchlist",
            "The exchange occurred after business hours"
        ]
    },
    {
        "id": 3,
        "title": "Sensitive data shared in a group channel",
        "severity": "medium",
        "sender": "Sarah Kim, M&A Analyst",
        "recipient": "M&A Strategy Group",
        "timestamp": "16:02 ET",
        "score": 76,
        "summary": "An employee posted preview financial assumptions in a broad group channel that included external vendors and consultants.",
        "reasons": [
            "Shared non-public financial assumptions",
            "Included external third parties",
            "Policy requires restricted handling of this content"
        ],
        "recommendedActions": [
            "Remove the content from the channel and preserve the thread",
            "Review access permissions for external collaborators",
            "Issue a reminder of restricted information handling policies"
        ],
        "department": "M&A",
        "evidence": [
            "The post included valuation ranges and timing assumptions",
            "Vendor access was not limited by role",
            "The message was visible to more users than necessary"
        ]
    },
    {
        "id": 4,
        "title": "Bulk download of restricted files",
        "severity": "high",
        "sender": "Liam Patel, Finance Analyst",
        "recipient": "Finance Shared Drive",
        "timestamp": "07:18 ET",
        "score": 91,
        "summary": "A finance analyst downloaded a large batch of restricted documents shortly before a planned departure from the company.",
        "reasons": [
            "Large number of downloads from restricted folders",
            "Activity occurred near a planned departure",
            "Files include customer pricing and P&L data"
        ],
        "recommendedActions": [
            "Revoke access and preserve device logs",
            "Notify HR and Security Operations",
            "Review downstream sharing for the downloaded files"
        ],
        "department": "Security",
        "evidence": [
            "Downloaded 43 files in a 12-minute window",
            "Folder permissions were broader than job requirements",
            "Access was initiated from a personal laptop"
        ]
    },
    {
        "id": 5,
        "title": "Suspicious off-hours document forwarding",
        "severity": "low",
        "sender": "Noor Hassan, Counsel",
        "recipient": "consulting-partner@firm.com",
        "timestamp": "22:41 ET",
        "score": 68,
        "summary": "An employee forwarded a draft merger memo to a consulting contact after normal working hours.",
        "reasons": [
            "Forwarded a draft document with non-public strategy details",
            "Recipient is not a sanctioned business partner",
            "Behavior indicates unusual timing"
        ],
        "recommendedActions": [
            "Request a copy of the forwarded document",
            "Review the employee's recent access history",
            "Add a monitoring flag for future off-hours transfers"
        ],
        "department": "Legal",
        "evidence": [
            "The forwarded file contained draft revenue projections",
            "The recipient address was not on the approved partner list",
            "The transfer was completed after 10 p.m."
        ]
    },
    {
        "id": 6,
        "title": "Encrypted message to a known market contact",
        "severity": "high",
        "sender": "Alicia Brooks, Equity Research",
        "recipient": "private-chat@securelink.com",
        "timestamp": "06:05 ET",
        "score": 89,
        "summary": "An equity research analyst exchanged a series of encrypted messages with a known market contact regarding an upcoming earnings call.",
        "reasons": [
            "Discussed upcoming earnings guidance prior to public disclosure",
            "Used an encrypted channel outside approved collaboration tools",
            "Established a recurring pattern of contact with an external market participant"
        ],
        "recommendedActions": [
            "Preserve the chat history and attachments",
            "Escalate to Investigations and Insider Risk",
            "Review recent trading activity in the analyst's network"
        ],
        "department": "Compliance",
        "evidence": [
            "The exchange referenced 'call notes' and 'preview numbers'",
            "The communication happened over a non-sanctioned messaging platform",
            "The contact is listed on the firm's restricted watchlist"
        ]
    }
]


@app.get('/api/model-status')
def model_status():
    endpoint = os.getenv('MODEL_ENDPOINT', 'http://127.0.0.1:11434/api/tags')
    model_name = os.getenv('MODEL_NAME', 'llama3.1:latest')
    is_custom = '/api/generate' not in endpoint and '/api/tags' not in endpoint

    if is_custom:
        backend = 'custom'
        check_url = endpoint
    else:
        backend = 'ollama'
        check_url = endpoint.rsplit('/api/', 1)[0] + '/api/tags' if '/api/generate' in endpoint else endpoint

    try:
        req = urllib.request.Request(check_url, method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            available = resp.status == 200
    except Exception:
        available = False

    return jsonify({
        'available': available,
        'model': model_name,
        'backend': backend if available else 'fallback',
    })


@app.get('/api/alerts')
def get_alerts():
    return jsonify(alerts)


@app.post('/api/upload')
def upload_data():
    if 'file' not in request.files:
        return jsonify({'error': 'Missing file'}), 400

    scoring_mode = request.args.get('mode', 'heuristic').lower()
    if scoring_mode not in {'heuristic', 'predictive'}:
        scoring_mode = 'heuristic'

    uploaded_file = request.files['file']
    filename = (uploaded_file.filename or '').lower()
    raw_bytes = uploaded_file.read()

    try:
        if filename.endswith('.json'):
            sample_data = json.loads(raw_bytes.decode('utf-8'))
        else:
            parsed_record = _parse_email_record(raw_bytes)
            sample_data = [parsed_record]
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON file'}), 400
    except Exception as exc:
        return jsonify({'error': f'Unable to parse uploaded file: {exc}'}), 400

    entries = []
    for record in sample_data:
        department = determine_department(record)
        heuristic_score = 90 if record.get('riskLevel') == 'high' else 72 if record.get('riskLevel') == 'medium' else 52
        predictive_score, prediction_explanation, feature_vector, model_name, model_version = score_with_model(record)
        if scoring_mode == 'predictive':
            score = predictive_score
        else:
            score = heuristic_score

        risk_signals = [
            signal for signal in [
                'risk_level',
                'external_recipient',
                'sensitive_content',
                'acquisition_context',
                'price_context',
                'personal_domain',
                'contains_forwarded',
                'contains_download',
            ] if feature_vector.get(signal)
        ]

        entry = {
            'id': len(alerts) + len(entries) + 1,
            'title': f"{record.get('source', 'message').capitalize()} risk from {record.get('sender', 'unknown')}",
            'severity': record.get('riskLevel', 'low'),
            'department': department,
            'sender': record.get('sender', 'unknown'),
            'recipient': record.get('recipient', record.get('channel', 'unknown')),
            'timestamp': record.get('timestamp', 'unknown'),
            'score': score,
            'heuristicScore': heuristic_score,
            'predictiveScore': predictive_score,
            'predictionExplanation': prediction_explanation,
            'featureVector': feature_vector,
            'riskSignals': risk_signals,
            'modelReady': True,
            'modelName': model_name,
            'modelVersion': model_version,
            'scoringStrategy': 'model',
            'summary': record.get('message', record.get('body', 'Sample risk event')),
            'scoringMode': scoring_mode,
            'reasons': [
                f"Triage: {department}",
                f"Source: {record.get('source', 'unknown')}",
                *[f"Tag: {tag}" for tag in _normalize_tags(record)]
            ],
            'recommendedActions': [
                'Review message content and sender intent',
                'Confirm whether external sharing is authorized',
                'Escalate to the assigned department if sensitive data is confirmed'
            ],
            'evidence': [
                *([record.get('subject')] if record.get('subject') else []),
                record.get('message', record.get('body', '')),
                f"Tags: {', '.join(_normalize_tags(record))}"
            ]
        }
        entries.append(entry)

    alerts.extend(entries)
    return jsonify({'added': len(entries), 'alerts': entries, 'scoringMode': scoring_mode})


@app.get('/')
def index():
    return send_from_directory('.', 'index.html')


@app.get('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)


@app.get('/sample_data/<path:filename>')
def sample_data_file(filename):
    return send_from_directory('sample_data', filename)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
