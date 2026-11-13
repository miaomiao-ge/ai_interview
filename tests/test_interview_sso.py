import base64
import hashlib
import hmac
import json
import time

import pytest

from core import interview_sso as sso


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def sign(payload: dict, secret: str = "test-secret") -> str:
    body = encode(json.dumps(payload).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return body + "." + encode(signature)


def payload(**overrides) -> dict:
    now = int(time.time())
    data = {
        "aud": "ai-interview",
        "passport_no": "P1234567",
        "source": "development",
        "iat": now,
        "exp": now + 120,
        "nonce": "nonce-1",
    }
    data.update(overrides)
    return data


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(sso, "INTERVIEW_SSO_SECRET", "test-secret")
    monkeypatch.setattr(sso, "get_redis_client", lambda: None)


def test_accepts_valid_ticket():
    result = sso.verify_sso_ticket(sign(payload()))
    assert result["passport_no"] == "P1234567"


def test_rejects_bad_signature():
    ticket = sign(payload(), secret="other-secret")
    with pytest.raises(sso.SSOTicketError) as error:
        sso.verify_sso_ticket(ticket)
    assert error.value.code == "sso_invalid"


def test_rejects_expired_ticket():
    with pytest.raises(sso.SSOTicketError) as error:
        sso.verify_sso_ticket(sign(payload(exp=int(time.time()) - 1)))
    assert error.value.code == "sso_expired"


def test_rejects_wrong_audience():
    with pytest.raises(sso.SSOTicketError) as error:
        sso.verify_sso_ticket(sign(payload(aud="other")))
    assert error.value.code == "sso_invalid"


def test_rejects_reused_nonce(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.used = False

        def set(self, key, value, nx=False, ex=None):
            if self.used:
                return False
            self.used = True
            return True

    fake = FakeRedis()
    monkeypatch.setattr(sso, "get_redis_client", lambda: fake)
    ticket = sign(payload(nonce="once"))
    assert sso.verify_sso_ticket(ticket)["nonce"] == "once"
    with pytest.raises(sso.SSOTicketError) as error:
        sso.verify_sso_ticket(ticket)
    assert error.value.code == "sso_reused"
