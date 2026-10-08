"""Practice contract tests, isolated from the production database and routers."""
import importlib
import sys
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from practice.sessions import PracticeError, Sessions

SECRET = 'practice-tests-only-secret-at-least-32-characters'


def token(uid=101, expired=False):
    return jwt.encode({'user_id': uid, 'passport_no': 'TEST', 'exp': time.time() + (-10 if expired else 600)}, SECRET, algorithm='HS256')


class FakeRecognizer:
    closed = False
    def start(self):
        pass
    def send(self, data):
        pass
    def finish(self):
        return 'A spoken practice answer.'
    def stop(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('JWT_SECRET_KEY', SECRET)
    module = importlib.import_module('practice.app')
    module.sessions = Sessions()
    monkeypatch.setattr(module.speech, 'recognizer', lambda *args: FakeRecognizer())
    with TestClient(module.app) as client:
        yield client, module


def headers(uid=101):
    return {'Authorization': 'Bearer ' + token(uid)}


def start(client):
    response = client.post('/api/sessions', json={'language': 'en'}, headers=headers())
    assert response.status_code == 200
    return response.json()


def test_auth_and_ownership(client):
    c, app = client
    assert c.post('/api/sessions', json={'language': 'en'}).status_code == 401
    assert c.post('/api/sessions', json={'language': 'en'}, headers={'Authorization': 'Bearer '+token(expired=True)}).status_code == 401
    session = start(c)
    assert c.get('/api/sessions/'+session['session_id']+'/audio', headers=headers(202)).status_code == 404
    c.delete('/api/sessions/'+session['session_id'], headers=headers(202))
    assert session['session_id'] in app.sessions.items
    c.delete('/api/sessions/'+session['session_id'], headers=headers())
    assert not app.sessions.items


def test_six_answers_end_without_record_or_grade(client):
    c, app = client
    session = start(c)
    sid = session['session_id']
    for turn in range(6):
        with c.websocket_connect('/api/ws', headers={'Origin': 'https://cryptollm.net'}) as ws:
            ws.send_json({'token': token(), 'session_id': sid, 'turn': turn})
            assert ws.receive_json()['type'] == 'ready'
            ws.send_bytes(b'\x00\x00' * 1600)
            ws.send_json({'action': 'finish'})
            answer = ws.receive_json()
            assert answer['type'] == 'answer'
            assert answer['completed'] == (turn == 5)
            assert not {'score', 'report', 'record_id', 'job_id'} & answer.keys()
    assert sid not in app.sessions.items
    assert app.active_asr == 0


def test_empty_audio_does_not_advance_and_releases_slot(client, monkeypatch):
    c, app = client
    monkeypatch.setattr(FakeRecognizer, 'finish', lambda self: '')
    session = start(c)
    with c.websocket_connect('/api/ws', headers={'Origin': 'https://cryptollm.net'}) as ws:
        ws.send_json({'token': token(), 'session_id': session['session_id'], 'turn': 0})
        assert ws.receive_json()['type'] == 'ready'
        ws.send_json({'action': 'finish', 'fallback_text': 'must not advance via text'})
        assert ws.receive_json()['code'] == 'asr_empty'
    assert app.sessions.items[session['session_id']].turn == 0
    assert app.sessions.items[session['session_id']].busy is False
    assert app.active_asr == 0


def test_ttl_capacity_rate_and_duplicate():
    now = [0]
    sessions = Sessions(capacity=1, ttl=10, hourly_limit=1, clock=lambda: now[0])
    sid, _ = sessions.create('a', 'zh')
    with pytest.raises(PracticeError, match='already_active'):
        sessions.create('a', 'zh')
    with pytest.raises(PracticeError, match='capacity'):
        sessions.create('b', 'en')
    now[0] = 11
    sessions.prune()
    assert sid not in sessions.items
    with pytest.raises(PracticeError, match='rate_limit'):
        sessions.create('a', 'zh')
    now[0] = 3601
    sessions.create('a', 'zh')


def test_disconnect_cleanup_and_no_production_routes(client):
    c, app = client
    session = start(c)
    with c.websocket_connect('/api/ws', headers={'Origin': 'https://cryptollm.net'}) as ws:
        ws.send_json({'token': token(), 'session_id': session['session_id'], 'turn': 0})
        assert ws.receive_json()['type'] == 'ready'
    assert not app.sessions.items[session['session_id']].busy
    assert app.active_asr == 0
    assert c.post('/api/user/end_interview', json={}).status_code == 404
    assert c.post('/api/user/upload_media').status_code == 404
    assert c.get('/health').json()['storage'] == 'memory'


def test_module_has_no_persistence_imports():
    # A fresh process prevents unrelated pytest plugins from contaminating this check.
    import subprocess
    result = subprocess.run([sys.executable, '-c',
        "import practice.app, sys; assert not any(n.startswith(('core.', 'routers.', 'sqlalchemy', 'redis')) for n in sys.modules)"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_origin_stale_turn_and_concurrent_recognition(client):
    from starlette.websockets import WebSocketDisconnect
    c, app = client
    session = start(c)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect('/api/ws', headers={'Origin': 'https://untrusted.invalid'}):
            pass
    hello = {'token': token(), 'session_id': session['session_id'], 'turn': 0}
    with c.websocket_connect('/api/ws', headers={'Origin': 'https://cryptollm.net'}) as first:
        first.send_json(hello)
        assert first.receive_json()['type'] == 'ready'
        with c.websocket_connect('/api/ws', headers={'Origin': 'https://cryptollm.net'}) as second:
            second.send_json(hello)
            assert second.receive_json()['code'] == 'capacity'
        assert app.active_asr == 1
        first.send_json({'action': 'finish'})
        assert first.receive_json()['type'] == 'answer'
    with c.websocket_connect('/api/ws', headers={'Origin': 'https://cryptollm.net'}) as stale:
        stale.send_json(hello)
        assert stale.receive_json()['code'] == 'stale_turn'
    assert app.active_asr == 0
