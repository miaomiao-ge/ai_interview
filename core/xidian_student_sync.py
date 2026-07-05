import hashlib
from dataclasses import asdict, dataclass
from datetime import date, datetime
from sqlalchemy import or_

from core.config import FACE_OSS_BUCKET_NAME, FACE_OSS_ENDPOINT
from core.database import SessionLocal, User
from core.oss_utils import upload_bytes_to_oss
from core.xidian_student_service import decode_official_photo, iter_applications


@dataclass
class SyncStats:
    received: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0


def _text(record: dict, key: str, limit: int) -> str:
    return str(record.get(key) or "").strip()[:limit]


def _date(record: dict, key: str) -> date | None:
    value = _text(record, key, 10)
    if not value:
        return None
    return date.fromisoformat(value)


def _password_hash_from_passport(passport_no: str) -> str:
    if len(passport_no) < 6:
        raise ValueError("护照号码不足 6 位，无法生成登录密码")
    return hashlib.sha256(passport_no[-6:].encode("utf-8")).hexdigest()


def _find_user(db, email: str, application_no: str):
    matches = db.query(User).filter(
        or_(User.email == email, User.xidian_application_no == application_no)
    ).all()
    if len(matches) > 1:
        raise ValueError("邮箱和申请编号分别属于不同用户，拒绝自动合并")
    return matches[0] if matches else None


def upsert_application(db, record: dict, upload_photo: bool = True) -> str:
    email = _text(record, "email", 100).lower()
    application_no = _text(record, "applicationNo", 50)
    if not email or "@" not in email:
        raise ValueError("申请数据缺少有效邮箱")
    if not application_no:
        raise ValueError("申请数据缺少申请编号")
    passport_no = _text(record, "passportNumber", 100)
    if not passport_no:
        raise ValueError("申请数据缺少护照号码")
    password_hash = _password_hash_from_passport(passport_no)

    user = _find_user(db, email, application_no)
    created = user is None
    if created:
        user = User(email=email, password_hash=password_hash, status="active")
        db.add(user)
        db.flush()

    owner = db.query(User).filter(User.passport_no == passport_no, User.id != user.id).first()
    if owner:
        raise ValueError("护照号码已属于其他用户")

    now = datetime.now()
    user.email = email
    user.real_name = _text(record, "name", 100)
    user.family_name = _text(record, "familyName", 100)
    user.given_name = _text(record, "givenName", 100)
    user.gender = _text(record, "genderName", 30)
    user.nationality = _text(record, "nationalityChAbName", 100)
    user.passport_no = passport_no
    user.password_hash = password_hash
    user.passport_expiry = _date(record, "expiryDate")
    user.birthday = _date(record, "birthday")
    user.xidian_application_no = application_no
    user.xidian_application_status = _text(record, "status", 50)
    user.source = "xidian_api"
    user.imported_at = now

    photo_value = str(record.get("photo") or "").strip()
    if upload_photo and photo_value:
        photo = decode_official_photo(photo_value)
        # A stable key makes repeated synchronization overwrite the same object
        # instead of leaving duplicate official photos in OSS.
        oss_key = f"face/official/{application_no}.{photo.extension}"
        upload_bytes_to_oss(
            photo.content,
            oss_key,
            True,
            endpoint=FACE_OSS_ENDPOINT,
            bucket_name=FACE_OSS_BUCKET_NAME,
            quiet=True,
        )
        user.face_image_oss_key = oss_key
        user.face_image_source = "xidian_official"
        user.face_enrolled_at = now
        user.official_photo_synced_at = now

    db.commit()
    return "created" if created else "updated"


def sync_students(
    year: int,
    application_nos: list[str] | None = None,
    upload_photo: bool = True,
    limit: int | None = None,
) -> dict:
    stats = SyncStats()
    errors = []
    for record in iter_applications(year, application_nos, limit=limit):
        stats.received += 1
        db = SessionLocal()
        try:
            action = upsert_application(db, record, upload_photo=upload_photo)
            setattr(stats, action, getattr(stats, action) + 1)
        except Exception as exc:
            db.rollback()
            stats.failed += 1
            errors.append(
                {
                    "application_no": _text(record, "applicationNo", 50),
                    "error": str(exc),
                }
            )
        finally:
            db.close()
    return {"year": year, "stats": asdict(stats), "errors": errors}
