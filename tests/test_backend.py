import importlib
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    assert alert['modelName']
    assert alert['modelVersion']
    assert alert['scoringStrategy'] == 'model'
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


def test_uploaded_record_exposes_model_ready_feature_contract():
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
    alert = payload['alerts'][0]
    assert alert['modelReady'] is True
    assert isinstance(alert['featureVector'], dict)
    assert alert['featureVector']['risk_level'] == 'high'
    assert alert['featureVector']['external_recipient'] == 1
    assert alert['featureVector']['personal_domain'] == 1
    assert isinstance(alert['riskSignals'], list)
    assert alert['riskSignals']


def test_external_slm_endpoint_can_drive_predictive_score(monkeypatch):
    """Test that a custom SLM endpoint receives the structured {record, featureVector} payload."""

    class SLMHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode('utf-8'))
            assert 'record' in payload, 'Expected record key in payload'
            assert 'featureVector' in payload, 'Expected featureVector key in payload'
            assert payload['record']['source'] == 'email'
            response = {
                'score': 81,
                'explanation': ['SLM signal detected an elevated risk posture.'],
                'modelName': 'tiny-risk-slm',
                'modelVersion': '1.0.0',
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(('127.0.0.1', 0), SLMHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    monkeypatch.setenv('MODEL_ENDPOINT', f'http://127.0.0.1:{port}/predict')
    monkeypatch.setenv('MODEL_NAME', 'tiny-risk-slm')
    monkeypatch.setenv('MODEL_VERSION', '1.0.0')

    import app as app_module
    importlib.reload(app_module)
    client = app_module.app.test_client()

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
    alert = payload['alerts'][0]
    assert alert['modelName'] == 'tiny-risk-slm'
    assert alert['predictiveScore'] == 81
    assert alert['scoringStrategy'] == 'model'

    server.shutdown()
    server.server_close()


def test_model_status_endpoint_returns_status():
    """Test the /api/model-status health check endpoint."""
    client = app.test_client()
    response = client.get('/api/model-status')
    assert response.status_code == 200
    data = response.get_json()
    assert 'available' in data
    assert 'model' in data
    assert 'backend' in data
    assert isinstance(data['available'], bool)
    assert data['backend'] in {'ollama', 'custom', 'fallback'}


def test_ollama_fallback_on_unreachable_endpoint(monkeypatch):
    """If the SLM endpoint is unreachable, scoring should fall back to the demo model."""
    monkeypatch.setenv('MODEL_ENDPOINT', 'http://127.0.0.1:19999/api/generate')
    monkeypatch.setenv('MODEL_TIMEOUT', '2')

    import app as app_module
    importlib.reload(app_module)

    from app import score_with_model
    record = {
        'source': 'email',
        'sender': 'Test User',
        'recipient': 'external@gmail.com',
        'riskLevel': 'high',
        'riskTags': ['sensitive'],
        'message': 'Confidential data shared externally.',
    }

    score, explanation, fv, model_name, model_version = score_with_model(record)
    assert model_name == 'demo-linear-risk-model'
    assert score >= 40
    assert isinstance(explanation, list)
    assert len(explanation) > 0
