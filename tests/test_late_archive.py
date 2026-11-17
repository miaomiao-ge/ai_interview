import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, InterviewRecord
from core.interview_job_service import backfill_archive


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_backfill_updates_record_when_media_arrives(db, monkeypatch):
    record = InterviewRecord(session_id="abc12345", user_email="x@y.z",
                             evaluate_status="success", archive_status="error")
    db.add(record)
    db.commit()

    monkeypatch.setattr(
        "core.interview_job_service.get_session_media",
        lambda sid: {"av": {"url": "https://oss/x.mkv", "oss_key": "records/x.mkv", "bytes": 10}},
    )

    result = backfill_archive(db, "abc12345")

    assert result["status"] == "success"
    db.refresh(record)
    assert record.archive_status == "success"
    assert record.av_path == "https://oss/x.mkv"


def test_backfill_is_noop_without_media(db, monkeypatch):
    record = InterviewRecord(session_id="def67890", archive_status="error")
    db.add(record)
    db.commit()

    monkeypatch.setattr("core.interview_job_service.get_session_media", lambda sid: {})

    result = backfill_archive(db, "def67890")

    assert result["status"] == "skipped"
