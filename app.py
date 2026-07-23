from flask import Flask, jsonify, send_from_directory, request
import json

app = Flask(__name__)


def _normalize_tags(record):
    tags = record.get('riskTags', [])
    if isinstance(tags, str):
        return [tags.lower()]
    return [str(tag).lower() for tag in tags]


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


def calculate_predictive_score(record):
    score = 35
    tags = _normalize_tags(record)
    source = record.get('source', '').lower()
    recipient = record.get('recipient', '').lower()
    message = ' '.join([
        record.get('message', ''),
        record.get('body', ''),
        record.get('subject', ''),
        ' '.join(tags),
        source,
        recipient,
    ]).lower()

    explanation = []
    risk_level = record.get('riskLevel', 'low').lower()
    if risk_level == 'high':
        score += 24
        explanation.append('High severity label increases the risk posture.')
    elif risk_level == 'medium':
        score += 14
        explanation.append('Medium severity label contributes to the score.')
    else:
        score += 6
        explanation.append('Low severity label provides a baseline risk increase.')

    feature_weights = {
        'external recipient': 16,
        'external contact': 14,
        'broker': 14,
        'trading': 12,
        'sensitive': 16,
        'restricted': 14,
        'encrypted': 10,
        'insider': 18,
        'legal': 8,
        'finance': 8,
        'pricing': 8,
        'customer pricing': 10,
        'p&l': 10,
        'm&a': 10,
        'acquisition': 12,
        'deal': 10,
        'confidential': 10,
        'personal': 9,
        'board prep': 8,
        'earnings': 7,
        'forwarded': 8,
        'download': 8,
    }

    for feature, weight in feature_weights.items():
        if feature in message:
            score += weight
            explanation.append(f"Matched signal '{feature}' with a weighted impact of {weight}.")

    if source in {'slack', 'teams'}:
        score += 4
        explanation.append('Collaboration-channel source adds a small risk lift.')

    if 'personal' in recipient or '@gmail.com' in recipient or '@outlook.com' in recipient:
        score += 8
        explanation.append('Personal or consumer email destination increases exposure.')

    if not explanation:
        explanation.append('No strong predictive features were detected beyond the baseline score.')

    return max(40, min(98, score)), explanation

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
    try:
        sample_data = json.load(uploaded_file)
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON file'}), 400

    entries = []
    for record in sample_data:
        department = determine_department(record)
        heuristic_score = 90 if record.get('riskLevel') == 'high' else 72 if record.get('riskLevel') == 'medium' else 52
        predictive_score, prediction_explanation = calculate_predictive_score(record)
        if scoring_mode == 'predictive':
            score = predictive_score
        else:
            score = heuristic_score

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
