from core import platform_account_sync as sync
from core.database import User
from core.platform_account_client import PlatformAccountError


class FakeQuery:
    def __init__(self, db):
        self.db = db

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.db.user


class FakeDb:
    def __init__(self, user=None):
        self.user = user
        self.added = None
        self.committed = False
        self.flushed = False

    def query(self, model):
        return FakeQuery(self)

    def add(self, user):
        self.added = user
        self.user = user

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def record(**overrides):
    data = {
        "id": 7,
        "passport_no": "p1234567",
        "email": "student@example.com",
        "real_name": "Student Name",
        "status": "active",
        "password_hash": "$2b$12$platform-hash",
    }
    data.update(overrides)
    return data


def test_normalize_passport_no():
    assert sync.normalize_passport_no(" p 123 456 ") == "P123456"


def test_creates_platform_account():
    db = FakeDb()
    action = sync.upsert_platform_student(db, record())
    assert action == "created"
    user = db.added
    assert user.passport_no == "P1234567"
    assert user.auth_source == "platform"
    assert user.source == "platform"
    assert user.password_hash == "$2b$12$platform-hash"
    assert user.platform_user_id == 7
    assert user.status == "active"


def test_links_existing_xidian_account_and_keeps_email():
    user = User(
        email="legacy@example.com",
        passport_no="P1234567",
        password_hash="legacy-hash",
        auth_source="xidian",
        status="active",
    )
    db = FakeDb(user)
    action = sync.upsert_platform_student(db, record())
    assert action == "linked"
    assert user.auth_source == "platform"
    assert user.password_hash == "$2b$12$platform-hash"
    assert user.email == "legacy@example.com"


def test_updates_existing_platform_account():
    user = User(
        email="old@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$old",
        auth_source="platform",
        status="active",
        platform_user_id=7,
        real_name="Old Name",
    )
    db = FakeDb(user)
    action = sync.upsert_platform_student(db, record())
    assert action == "updated"
    assert user.email == "old@example.com"
    assert user.password_hash == "$2b$12$platform-hash"


def test_unchanged_platform_account_is_skipped():
    user = User(
        email="student@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="platform",
        status="active",
        platform_user_id=7,
        real_name="Student Name",
    )
    db = FakeDb(user)
    assert sync.upsert_platform_student(db, record()) == "skipped"


def test_dry_run_does_not_write():
    db = FakeDb()
    assert sync.upsert_platform_student(db, record(), dry_run=True) == "created"
    assert db.added is None


def test_ensure_pulls_account_on_demand(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(sync, "fetch_student", lambda passport_no: record())
    user, error = sync.ensure_local_account_from_platform(db, " P 1234567 ")
    assert error is None
    assert user is db.added
    assert db.committed is True


def test_ensure_reports_missing_account(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(sync, "fetch_student", lambda passport_no: None)
    assert sync.ensure_local_account_from_platform(db, "P1") == (None, "not_found")


def test_ensure_reports_unavailable_platform(monkeypatch):
    db = FakeDb()

    def boom(passport_no):
        raise PlatformAccountError("down")

    monkeypatch.setattr(sync, "fetch_student", boom)
    assert sync.ensure_local_account_from_platform(db, "P1") == (None, "unavailable")
