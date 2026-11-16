from datetime import datetime

from core import platform_account_sync as sync
from core.database import User
from core.platform_account_client import PlatformAccountError


TEST_SOURCE = {"name": "test", "base": "http://platform.test", "token": "test-token"}


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
    monkeypatch.setattr(sync, "fetch_students", lambda passport_no, source_name=None: [(TEST_SOURCE, record())])
    user, error = sync.ensure_local_account_from_platform(db, " P 1234567 ")
    assert error is None
    assert user is db.added
    assert db.committed is True


def test_ensure_pulls_account_by_email(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(sync, "fetch_students", lambda account, source_name=None: [(TEST_SOURCE, record())])
    user, error = sync.ensure_local_account_from_platform(db, "student@example.com")
    assert error is None
    assert user is db.added
    assert db.committed is True


def test_ensure_reports_missing_passport(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(sync, "fetch_students", lambda account, source_name=None: [(TEST_SOURCE, record(passport_no=""))])
    assert sync.ensure_local_account_from_platform(db, "student@example.com") == (None, "missing_passport")


def test_ensure_reports_missing_account(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(sync, "fetch_students", lambda passport_no, source_name=None: [])
    assert sync.ensure_local_account_from_platform(db, "P1") == (None, "not_found")


def test_ensure_reports_unavailable_platform(monkeypatch):
    db = FakeDb()

    def boom(passport_no, source_name=None):
        raise PlatformAccountError("down")

    monkeypatch.setattr(sync, "fetch_students", boom)
    assert sync.ensure_local_account_from_platform(db, "P1") == (None, "unavailable")


def test_creates_xidian_roster_account_for_xidian_entry():
    db = FakeDb()
    action = sync.upsert_platform_student(db, record(source="xidian_api"))
    assert action == "created"
    user = db.added
    assert user.auth_source == "xidian"
    assert user.source == "xidian_api"
    assert user.password_hash == "$2b$12$platform-hash"


def test_xidian_snapshot_with_same_password_stays_on_xidian_entry():
    user = User(
        email="legacy@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="xidian",
        status="active",
    )
    db = FakeDb(user)
    action = sync.upsert_platform_student(db, record(source="xidian_api"))
    assert action == "updated"
    assert user.auth_source == "xidian"
    assert user.source == "xidian_api"
    assert user.password_hash == "$2b$12$platform-hash"


def test_previously_linked_roster_account_is_restored_to_xidian():
    user = User(
        email="legacy@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="platform",
        status="active",
        source="platform",
        platform_user_id=7,
        real_name="Student Name",
    )
    db = FakeDb(user)
    action = sync.upsert_platform_student(db, record(source="xidian_api"))
    assert action == "restored"
    assert user.auth_source == "xidian"
    assert user.source == "xidian_api"
    assert user.password_hash == "$2b$12$platform-hash"


def test_xidian_snapshot_with_changed_password_is_a_conflict():
    user = User(
        email="legacy@example.com",
        passport_no="P1234567",
        password_hash="ai-changed-password",
        auth_source="xidian",
        status="active",
    )
    db = FakeDb(user)
    action = sync.upsert_platform_student(db, record(source="xidian_api"))
    assert action == "conflict"
    assert user.auth_source == "xidian"
    assert user.password_hash == "ai-changed-password"


def test_test_source_is_skipped():
    user = User(
        email="legacy@example.com",
        passport_no="P1234567",
        password_hash="anything",
        auth_source="xidian",
        status="active",
    )
    db = FakeDb(user)
    assert sync.upsert_platform_student(db, record(source="qa")) == "skipped"


def test_copies_platform_official_face_key():
    user = User(
        email="legacy@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="xidian",
        status="active",
        face_image_oss_key="",
    )
    db = FakeDb(user)
    sync.upsert_platform_student(
        db,
        record(
            source="xidian_api",
            face_image_oss_key="face/official/P1234567.jpg",
            face_image_source="xidian_official",
            has_photo=True,
        ),
    )
    assert user.face_image_oss_key == "face/official/P1234567.jpg"
    assert user.face_image_source == "xidian_official"


def test_existing_ai_face_is_not_overwritten():
    user = User(
        email="legacy@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="xidian",
        status="active",
        face_image_oss_key="face/ai/enrolled.jpg",
    )
    db = FakeDb(user)
    sync.upsert_platform_student(
        db,
        record(
            source="xidian_api",
            face_image_oss_key="face/official/P1234567.jpg",
            has_photo=True,
        ),
    )
    assert user.face_image_oss_key == "face/ai/enrolled.jpg"


def test_fetches_minio_photo_and_uploads_to_ai_oss(monkeypatch):
    user = User(
        email="legacy@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="xidian",
        status="active",
        face_image_oss_key="",
    )
    db = FakeDb(user)
    calls = []

    monkeypatch.setattr(
        sync,
        "fetch_student_photo",
        lambda account, source=None: {"kind": "bytes", "content": b"image-bytes", "extension": "jpg"},
    )

    def fake_upload(content, key, overwrite, **kwargs):
        calls.append((content, key, overwrite, kwargs))

    monkeypatch.setattr(sync, "upload_bytes_to_oss", fake_upload)
    sync.upsert_platform_student(
        db,
        record(source="platform_local", has_photo=True),
    )
    assert user.face_image_oss_key.startswith("face/platform/p1234567-")
    assert user.face_image_oss_key.endswith(".jpg")
    assert user.face_image_source == "platform_profile"
    assert calls and calls[0][0] == b"image-bytes"


def test_photo_version_change_refreshes_existing_face(monkeypatch):
    user = User(
        email="student@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="platform",
        status="active",
        face_image_oss_key="face/platform/p1234567-old.jpg",
        face_image_source="platform_profile",
        platform_photo_version="profile:1:aaa",
    )
    db = FakeDb(user)
    uploaded = []
    monkeypatch.setattr(
        sync,
        "fetch_student_photo",
        lambda account, source=None: {"kind": "bytes", "content": b"new-photo", "extension": "jpg"},
    )
    monkeypatch.setattr(sync, "upload_bytes_to_oss", lambda content, key, overwrite, **kwargs: uploaded.append(key))

    sync.upsert_platform_student(
        db,
        record(source="platform_local", has_photo=True, photo_version="profile:2:bbb"),
    )

    assert user.face_image_oss_key != "face/platform/p1234567-old.jpg"
    assert user.face_image_oss_key.startswith("face/platform/p1234567-")
    assert user.platform_photo_version == "profile:2:bbb"
    assert uploaded == [user.face_image_oss_key]


def test_same_photo_version_keeps_existing_face(monkeypatch):
    user = User(
        email="student@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="platform",
        status="active",
        face_image_oss_key="face/platform/p1234567-current.jpg",
        platform_photo_version="profile:2:bbb",
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("photo must not be fetched when its version is unchanged")

    monkeypatch.setattr(sync, "fetch_student_photo", unexpected)
    sync.upsert_platform_student(
        FakeDb(user),
        record(source="platform_local", has_photo=True, photo_version="profile:2:bbb"),
    )
    assert user.face_image_oss_key == "face/platform/p1234567-current.jpg"


def test_missing_stored_photo_version_adopts_current_without_refresh(monkeypatch):
    user = User(
        email="student@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="platform",
        status="active",
        face_image_oss_key="face/platform/p1234567-existing.jpg",
        platform_photo_version="",
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("existing face must not be re-downloaded during version backfill")

    monkeypatch.setattr(sync, "fetch_student_photo", unexpected)
    sync.upsert_platform_student(
        FakeDb(user),
        record(source="platform_local", has_photo=True, photo_version="profile:3:ccc"),
    )
    assert user.face_image_oss_key == "face/platform/p1234567-existing.jpg"
    assert user.platform_photo_version == "profile:3:ccc"


def test_newer_platform_photo_refreshes_when_stored_version_is_missing(monkeypatch):
    user = User(
        email="student@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="platform",
        status="active",
        face_image_oss_key="face/platform/p1234567-old.jpg",
        face_enrolled_at=datetime(2026, 11, 1, 9, 0),
        platform_photo_version="",
    )
    uploaded = []
    monkeypatch.setattr(
        sync,
        "fetch_student_photo",
        lambda account, source=None: {"kind": "bytes", "content": b"newer-photo", "extension": "jpg"},
    )
    monkeypatch.setattr(sync, "upload_bytes_to_oss", lambda content, key, overwrite, **kwargs: uploaded.append(key))

    sync.upsert_platform_student(
        FakeDb(user),
        record(
            source="platform_local",
            has_photo=True,
            photo_version="profile:2:bbb",
            photo_updated_at="2026-11-15T10:00:00",
        ),
    )

    assert user.face_image_oss_key != "face/platform/p1234567-old.jpg"
    assert user.platform_photo_version == "profile:2:bbb"
    assert uploaded == [user.face_image_oss_key]


def test_profile_photo_overrides_official_face_even_when_older(monkeypatch):
    user = User(
        email="student@example.com",
        passport_no="P1234567",
        password_hash="$2b$12$platform-hash",
        auth_source="xidian",
        status="active",
        face_image_oss_key="face/official/P1234567.jpg",
        face_image_source="xidian_official",
        face_enrolled_at=datetime(2026, 11, 15, 9, 0),
        platform_photo_version="",
    )
    uploaded = []
    monkeypatch.setattr(
        sync,
        "fetch_student_photo",
        lambda account, source=None: {"kind": "bytes", "content": b"profile-photo", "extension": "jpg"},
    )
    monkeypatch.setattr(sync, "upload_bytes_to_oss", lambda content, key, overwrite, **kwargs: uploaded.append(key))

    sync.upsert_platform_student(
        FakeDb(user),
        record(
            source="platform_local",
            has_photo=True,
            photo_source="profile",
            photo_version="profile:9:zzz",
            photo_updated_at="2026-11-01T10:00:00",
        ),
    )

    assert user.face_image_oss_key.startswith("face/platform/p1234567-")
    assert user.face_image_source == "platform_profile"
    assert user.platform_photo_version == "profile:9:zzz"
    assert uploaded == [user.face_image_oss_key]
