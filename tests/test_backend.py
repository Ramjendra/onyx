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
