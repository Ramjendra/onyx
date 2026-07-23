import io
import json

from app import app


def test_alerts_endpoint_returns_risk_data():
    client = app.test_client()
    response = client.get('/api/alerts')

    assert response.status_code == 200
    payload = json.loads(response.data)
    assert isinstance(payload, list)
    assert len(payload) >= 4
    assert payload[0]['title']
    assert payload[0]['severity'] in {'high', 'medium', 'low'}
    assert any(item['severity'] == 'high' for item in payload)


def test_predictive_upload_mode_returns_predictive_score():
    client = app.test_client()
    sample_payload = [{
        'source': 'email',
        'sender': 'Maya Chen',
        'recipient': 'personal-email@domain.com',
        'timestamp': '08:43 ET',
        'riskLevel': 'high',
        'riskTags': ['external recipient', 'sensitive', 'deal'],
        'message': 'Forwarded confidential board prep details to a personal account.'
    }]

    response = client.post(
        '/api/upload?mode=predictive',
        data={'file': (io.BytesIO(json.dumps(sample_payload).encode('utf-8')), 'sample.json')},
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['added'] == 1
    alert = payload['alerts'][0]
    assert alert['scoringMode'] == 'predictive'
    assert alert['heuristicScore'] == 90
    assert alert['predictiveScore'] >= 70
    assert alert['score'] == alert['predictiveScore']
    assert isinstance(alert['predictionExplanation'], list)
    assert alert['predictionExplanation']


def test_raw_email_upload_is_parsed_into_risk_record():
    client = app.test_client()
    raw_email = b"""From: michael.tan@businesscorp.com\nTo: jane.doe@gmail.com\nSubject: Confidential acquisition pricing model\nDate: Tue, 21 Jul 2026 09:12:00 +0000\n\nHi Jane, please see the attached acquisition pricing model for the target company. This is still confidential and not for external distribution.\n"""

    response = client.post(
        '/api/upload?mode=predictive',
        data={'file': (io.BytesIO(raw_email), 'sample.eml')},
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['added'] == 1
    alert = payload['alerts'][0]
    assert alert['sender'] == 'michael.tan@businesscorp.com'
    assert alert['recipient'] == 'jane.doe@gmail.com'
    assert alert['summary']
    assert alert['predictiveScore'] >= 70
