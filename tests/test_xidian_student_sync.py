import base64
from types import SimpleNamespace

import pytest

from core import xidian_student_service as service
from core import xidian_student_sync as sync


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return FakeResponse({"result": "1", "valid": True, "dataObject": "token"})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse(
            {
                "result": "1",
                "valid": True,
                "dataObject": {"totalCount": 0, "data": []},
            }
        )


def test_api_uses_query_credentials_and_form_body(monkeypatch):
    monkeypatch.setattr(service, "XIDIAN_STUDENT_APP_KEY", "key")
    monkeypatch.setattr(service, "XIDIAN_STUDENT_APP_SECRET", "secret")
    client = FakeClient()

    token = service.get_access_token(client)
    service.get_application_page(client, token, 2026, 1)

    assert client.calls[0][2]["params"] == {"appKey": "key", "appSecret": "secret"}
    assert client.calls[1][2]["data"] == {
        "token": "token",
        "year": "2026",
        "pageNum": "1",
        "pageSize": "100",
    }
    assert client.calls[1][2]["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_decode_official_photo_accepts_jpeg():
    raw = b"\xff\xd8\xfftest-photo"
    photo = service.decode_official_photo(base64.b64encode(raw).decode())
    assert photo.content == raw
    assert photo.extension == "jpg"


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def all(self):
        return []

    def first(self):
        return self.result


class FakeDb:
    def __init__(self):
        self.user = None
        self.committed = False

    def query(self, model):
        return FakeQuery(None)

    def add(self, user):
        self.user = user

    def flush(self):
        self.user.id = 7

    def commit(self):
        self.committed = True


def test_upsert_application_maps_all_fields_without_photo():
    db = FakeDb()
    action = sync.upsert_application(
        db,
        {
            "applicationNo": "20260600003",
            "name": "DU TEST",
            "familyName": "TEST",
            "givenName": "DU",
            "genderName": "女",
            "nationalityChAbName": "奥兰群岛",
            "passportNumber": "AQ1234567",
            "expiryDate": "2026-07-03",
            "birthday": "2026-06-02",
            "email": "Student@example.com",
            "status": "已录取",
        },
        upload_photo=False,
    )

    assert action == "created"
    assert db.committed is True
    assert db.user.email == "student@example.com"
    assert db.user.xidian_application_no == "20260600003"
    assert db.user.nationality == "奥兰群岛"
    assert db.user.passport_expiry.isoformat() == "2026-07-03"
    assert db.user.password_hash == sync._password_hash_from_passport("AQ1234567")


def test_password_hash_from_passport_rejects_short_passport_number():
    with pytest.raises(ValueError, match="不足 6 位"):
        sync._password_hash_from_passport("A1234")
