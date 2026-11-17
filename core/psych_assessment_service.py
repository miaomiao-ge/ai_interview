import json
from datetime import datetime
from typing import Optional

from core.assessment import load_instrument, score_answers, validate_answers
from core.database import PsychAssessment, User


def latest_for_user(db, user_id: int) -> Optional[PsychAssessment]:
    return (
        db.query(PsychAssessment)
        .filter(PsychAssessment.user_id == user_id)
        .order_by(PsychAssessment.attempt_no.desc(), PsychAssessment.id.desc())
        .first()
    )


def _next_attempt(db, user_id: int) -> int:
    latest = (
        db.query(PsychAssessment)
        .filter(PsychAssessment.user_id == user_id, PsychAssessment.status != "draft")
        .order_by(PsychAssessment.attempt_no.desc())
        .first()
    )
    return 1 if latest is None else (latest.attempt_no or 0) + 1


def _instrument_meta() -> tuple:
    instrument = load_instrument()
    return instrument["instrument"], instrument["version"]


def _base_record(db, user: User, status: str, consent_version: str) -> PsychAssessment:
    instrument, version = _instrument_meta()
    return PsychAssessment(
        user_id=user.id,
        user_email=user.email or "",
        instrument=instrument,
        version=version,
        attempt_no=_next_attempt(db, user.id),
        status=status,
        consent_version=consent_version or "",
    )


def save_draft(db, user: User, answers: dict, consent_version: str) -> PsychAssessment:
    payload = json.dumps({str(k): int(v) for k, v in (answers or {}).items()})
    existing = (
        db.query(PsychAssessment)
        .filter(
            PsychAssessment.user_id == user.id,
            PsychAssessment.status == "draft",
        )
        .order_by(PsychAssessment.attempt_no.desc())
        .first()
    )
    if existing:
        existing.answers_json = payload
        if consent_version:
            existing.consent_version = consent_version
        db.commit()
        db.refresh(existing)
        return existing

    record = _base_record(db, user, "draft", consent_version)
    record.answers_json = payload
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def submit_assessment(db, user: User, answers: dict, consent_version: str) -> PsychAssessment:
    error = validate_answers(answers)
    if error:
        raise ValueError(error)

    scored = score_answers(answers)
    record = _base_record(db, user, "submitted", consent_version)
    record.answers_json = json.dumps({str(k): int(v) for k, v in answers.items()})
    record.dimension_json = json.dumps(scored["dimensions"], ensure_ascii=False)
    record.gsi = scored["gsi"]
    record.pst = scored["pst"]
    record.psdi = scored["psdi"]
    record.risk_level = scored["risk_level"]
    record.risk_items_json = json.dumps(scored["risk_items"], ensure_ascii=False)
    record.submitted_at = datetime.now()
    db.add(record)

    db.query(PsychAssessment).filter(
        PsychAssessment.user_id == user.id,
        PsychAssessment.status == "draft",
    ).delete(synchronize_session=False)

    db.commit()
    db.refresh(record)
    return record


def skip_assessment(db, user: User, reason: str) -> PsychAssessment:
    record = _base_record(db, user, "skipped", "")
    record.skip_reason = (reason or "")[:255]
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def has_submitted(db, user_id: int) -> bool:
    return (
        db.query(PsychAssessment)
        .filter(PsychAssessment.user_id == user_id, PsychAssessment.status == "submitted")
        .first()
        is not None
    )
