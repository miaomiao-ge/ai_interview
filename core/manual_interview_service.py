from datetime import datetime, timedelta
from typing import List, Optional

from core.database import ManualInterviewRequest, User

PENDING = "pending"
CONTACTED = "contacted"
DONE = "done"
VALID_STATUS = {PENDING, CONTACTED, DONE}


def create_request(db, user: User, reason: str, note: str) -> ManualInterviewRequest:
    since = datetime.now() - timedelta(hours=24)
    recent = (
        db.query(ManualInterviewRequest)
        .filter(
            ManualInterviewRequest.user_id == user.id,
            ManualInterviewRequest.created_at >= since,
        )
        .order_by(ManualInterviewRequest.id.desc())
        .first()
    )
    if recent:
        return recent

    record = ManualInterviewRequest(
        user_id=user.id,
        user_email=user.email or "",
        passport_no=getattr(user, "passport_no", "") or "",
        reason=(reason or "")[:50],
        note=(note or "")[:255],
        status=PENDING,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_requests(db, status: str = "", limit: int = 50) -> List[ManualInterviewRequest]:
    query = db.query(ManualInterviewRequest)
    if status:
        query = query.filter(ManualInterviewRequest.status == status)
    return query.order_by(ManualInterviewRequest.id.desc()).limit(limit).all()


def mark_status(db, request_id: int, status: str, handled_by: str) -> Optional[ManualInterviewRequest]:
    if status not in VALID_STATUS:
        raise ValueError("invalid status")
    record = db.query(ManualInterviewRequest).filter(ManualInterviewRequest.id == request_id).first()
    if not record:
        return None
    record.status = status
    record.handled_by = handled_by or ""
    record.handled_at = datetime.now()
    db.commit()
    db.refresh(record)
    return record
