"""Mirror platform student accounts into the AI interview users table.

The platform owns the password for students who registered there. Xidian-sourced
accounts keep their own initial password until the same passport registers on the
platform, at which point the platform becomes authoritative.
"""
import re
from dataclasses import asdict, dataclass
from datetime import datetime

from core.database import SessionLocal, User
from core.platform_account_client import PlatformAccountError, fetch_student, iter_students


@dataclass
class SyncStats:
    received: int = 0
    created: int = 0
    updated: int = 0
    linked: int = 0
    skipped: int = 0
    failed: int = 0


def normalize_passport_no(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def _text(record: dict, key: str, limit: int) -> str:
    return str(record.get(key) or "").strip()[:limit]


def _password_hash(record: dict) -> str:
    return str(record.get("password_hash") or "").strip()


def _email(record: dict, passport_no: str) -> str:
    email = _text(record, "email", 100).lower()
    if not email or "@" not in email:
        return f"{passport_no.lower()}@platform.invalid"
    return email


def _platform_id(record: dict):
    try:
        return int(record.get("id"))
    except (TypeError, ValueError):
        return None


def _differs(user: User, record: dict) -> bool:
    # Email is intentionally excluded: existing accounts keep the address their
    # interview records may have been keyed by.
    return (
        (user.password_hash or "") != _password_hash(record)
        or (user.status or "active") != str(record.get("status") or "active")
        or (user.real_name or "") != _text(record, "real_name", 100)
        or getattr(user, "platform_user_id", None) != _platform_id(record)
    )


def upsert_platform_student(db, record: dict, dry_run: bool = False) -> str:
    passport_no = normalize_passport_no(_text(record, "passport_no", 100))
    if not passport_no:
        raise ValueError("平台账号缺少护照号")
    password_hash = _password_hash(record)
    if not password_hash:
        raise ValueError("平台账号缺少密码哈希")

    status_value = str(record.get("status") or "active").strip() or "active"
    real_name = _text(record, "real_name", 100)
    platform_id = _platform_id(record)

    user = db.query(User).filter(User.passport_no == passport_no).first()
    now = datetime.now()

    if user is None:
        action = "created"
        if not dry_run:
            user = User(
                email=_email(record, passport_no),
                real_name=real_name,
                passport_no=passport_no,
                password_hash=password_hash,
                status=status_value,
                source="platform",
                auth_source="platform",
                platform_user_id=platform_id,
                platform_synced_at=now,
            )
            db.add(user)
            db.flush()
        return action

    auth_source = getattr(user, "auth_source", None) or "xidian"
    if auth_source == "platform":
        action = "updated" if _differs(user, record) else "skipped"
        if action == "skipped" or dry_run:
            return action
        user.password_hash = password_hash
    else:
        # A platform registration takes over an existing Xidian account. Keep the
        # original email and all Xidian application fields.
        action = "linked"
        if dry_run:
            return action
        user.auth_source = "platform"
        user.source = "platform"
        user.password_hash = password_hash

    user.real_name = real_name or user.real_name
    user.status = status_value
    user.platform_user_id = platform_id
    user.platform_synced_at = now
    db.flush()
    return action


def sync_platform_students(limit: int | None = None, dry_run: bool = False) -> dict:
    stats = SyncStats()
    errors = []
    for record in iter_students(limit=limit):
        stats.received += 1
        db = SessionLocal()
        try:
            action = upsert_platform_student(db, record, dry_run=dry_run)
            if dry_run:
                db.rollback()
            else:
                db.commit()
            setattr(stats, action, getattr(stats, action) + 1)
        except Exception as exc:
            db.rollback()
            stats.failed += 1
            errors.append({"platform_user_id": _platform_id(record), "error": str(exc)})
        finally:
            db.close()
    return {"stats": asdict(stats), "errors": errors, "dry_run": dry_run}


def ensure_local_account_from_platform(db, passport_no: str) -> tuple[User | None, str | None]:
    """Pull one account at login time so a fresh registration works immediately.

    Returns (user, error_code). error_code is "not_found" or "unavailable".
    The caller commits the session after a successful upsert.
    """
    passport_no = normalize_passport_no(passport_no)
    if not passport_no:
        return None, "not_found"
    try:
        record = fetch_student(passport_no)
    except PlatformAccountError:
        return None, "unavailable"
    if not record:
        return None, "not_found"
    if normalize_passport_no(_text(record, "passport_no", 100)) != passport_no:
        return None, "not_found"
    try:
        upsert_platform_student(db, record)
    except ValueError:
        return None, "not_found"
    db.commit()
    return db.query(User).filter(User.passport_no == passport_no).first(), None
