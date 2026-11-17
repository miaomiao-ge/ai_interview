import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, User
from core.psych_assessment_service import (
    has_submitted,
    latest_for_user,
    save_draft,
    skip_assessment,
    submit_assessment,
)


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
    row = User(email="psych@example.com", real_name="测评", password_hash="x", status="active")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _answers(value=1):
    return {no: value for no in range(1, 54)}


def test_draft_is_saved_and_readable(db, user):
    record = save_draft(db, user, {1: 2}, "v1")

    assert record.status == "draft"
    assert latest_for_user(db, user.id).answers_json == '{"1": 2}'


def test_submit_scores_and_marks_submitted(db, user):
    record = submit_assessment(db, user, _answers(1), "v1")

    assert record.status == "submitted"
    assert record.pst == 53
    assert record.gsi == 1.0
    assert record.risk_level == "WATCH"
    assert has_submitted(db, user.id) is True


def test_draft_does_not_satisfy_gate(db, user):
    save_draft(db, user, {1: 2}, "v1")

    assert has_submitted(db, user.id) is False


def test_skip_does_not_satisfy_gate(db, user):
    record = skip_assessment(db, user, "不想填写")

    assert record.status == "skipped"
    assert has_submitted(db, user.id) is False


def test_resubmit_creates_new_attempt(db, user):
    first = submit_assessment(db, user, _answers(0), "v1")
    second = submit_assessment(db, user, _answers(1), "v1")

    assert first.attempt_no == 1
    assert second.attempt_no == 2
    assert latest_for_user(db, user.id).id == second.id


def test_submit_rejects_incomplete_answers(db, user):
    with pytest.raises(ValueError):
        submit_assessment(db, user, {1: 1}, "v1")
