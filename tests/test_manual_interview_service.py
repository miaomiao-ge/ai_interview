import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, User
from core.manual_interview_service import create_request, list_requests, mark_status


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db):
    row = User(email="manual@example.com", real_name="人工", password_hash="x",
               status="active", passport_no="E1234567")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_create_request_records_student_and_note(db, user):
    record = create_request(db, user, "device", "麦克风坏了")

    assert record.status == "pending"
    assert record.passport_no == "E1234567"
    assert record.note == "麦克风坏了"


def test_create_request_is_idempotent_within_a_day(db, user):
    first = create_request(db, user, "device", "")
    second = create_request(db, user, "network", "第二次")

    assert second.id == first.id
    assert len(list_requests(db)) == 1


def test_mark_status_updates_pending_request(db, user):
    record = create_request(db, user, "device", "")

    updated = mark_status(db, record.id, "contacted", "teacher-a")

    assert updated.status == "contacted"
    assert updated.handled_by == "teacher-a"
    assert updated.handled_at is not None


def test_list_requests_filters_by_status(db, user):
    record = create_request(db, user, "device", "")
    mark_status(db, record.id, "done", "teacher-a")

    assert list_requests(db, status="pending") == []
    assert len(list_requests(db, status="done")) == 1
