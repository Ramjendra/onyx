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
