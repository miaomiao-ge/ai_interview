import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INITIAL_PASSWORD_SUFFIX = "2026"
SUPPORTED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def normalize_email(value: str | None) -> str:
    return clean_value(value).lower()


def normalize_passport_no(value: str | None) -> str:
    return re.sub(r"\s+", "", clean_value(value)).upper()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def password_from_passport(passport_no: str) -> str:
    passport = normalize_passport_no(passport_no)
    if not passport:
        raise ValueError("passport_no is required to generate the default password")
    return f"{passport}{INITIAL_PASSWORD_SUFFIX}"


def parse_date(value: str | None):
    value = clean_value(value)
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def get_photo_extension(photo_path: Path) -> str:
    extension = photo_path.suffix.lower().lstrip(".")
    if extension not in SUPPORTED_PHOTO_EXTENSIONS:
        raise ValueError(
            f"Unsupported photo extension: {extension}. "
            f"Use one of: {', '.join(sorted(SUPPORTED_PHOTO_EXTENSIONS))}"
        )
    return "jpg" if extension == "jpeg" else extension


def upload_face_photo(photo_path: Path, passport_no: str) -> str:
    from core.config import FACE_OSS_BUCKET_NAME, FACE_OSS_ENDPOINT
    from core.oss_utils import upload_bytes_to_oss

    if not photo_path.is_file():
        raise FileNotFoundError(str(photo_path))
    extension = get_photo_extension(photo_path)
    oss_key = f"face/candidates/{passport_no}/{uuid4().hex}.{extension}"
    upload_bytes_to_oss(
        photo_path.read_bytes(),
        oss_key,
        True,
        endpoint=FACE_OSS_ENDPOINT,
        bucket_name=FACE_OSS_BUCKET_NAME,
    )
    return oss_key


def build_candidate(args) -> dict:
    passport_no = normalize_passport_no(args.passport_no)
    if not passport_no:
        raise ValueError("--passport-no is required")

    password = clean_value(args.password) or password_from_passport(passport_no)
    return {
        "email": normalize_email(args.email),
        "real_name": clean_value(args.name),
        "passport_no": passport_no,
        "password": password,
        "xidian_application_no": clean_value(args.application_no) or None,
        "xidian_application_id": clean_value(args.application_id) or None,
        "xidian_recommend_flag": clean_value(args.recommend_flag),
        "xidian_application_status": clean_value(args.application_status),
        "family_name": clean_value(args.family_name),
        "given_name": clean_value(args.given_name),
        "gender": clean_value(args.gender),
        "nationality": clean_value(args.nationality),
        "passport_expiry": parse_date(args.passport_expiry),
        "birthday": parse_date(args.birthday),
        "remark": clean_value(args.remark),
        "source": clean_value(args.source) or "manual_single_import",
        "status": clean_value(args.status) or "active",
    }


def upsert_manual_candidate(args) -> dict:
    candidate = build_candidate(args)
    photo_path = Path(args.photo).expanduser().resolve() if args.photo else None

    report = {
        "dry_run": args.dry_run,
        "passport_no": candidate["passport_no"],
        "email": candidate["email"],
        "initial_password": candidate["password"],
        "photo": str(photo_path) if photo_path else "",
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    if args.dry_run:
        report["action"] = "validated"
        report["face_image_oss_key"] = ""
        return report

    from sqlalchemy import or_

    from core.database import SessionLocal, User, init_db

    init_db()
    face_image_oss_key = ""
    if photo_path:
        face_image_oss_key = upload_face_photo(photo_path, candidate["passport_no"])

    db = SessionLocal()
    try:
        now = datetime.now()
        lookup_filters = [User.passport_no == candidate["passport_no"]]
        if candidate["xidian_application_no"]:
            lookup_filters.append(User.xidian_application_no == candidate["xidian_application_no"])
        if candidate["xidian_application_id"]:
            lookup_filters.append(User.xidian_application_id == candidate["xidian_application_id"])

        user = db.query(User).filter(or_(*lookup_filters)).order_by(User.id.asc()).first()
        created = user is None
        if created:
            user = User(passport_no=candidate["passport_no"])
            db.add(user)

        user.email = candidate["email"]
        user.real_name = candidate["real_name"]
        user.password_hash = hash_password(candidate["password"])
        user.status = candidate["status"]
        user.xidian_application_no = candidate["xidian_application_no"]
        user.xidian_application_id = candidate["xidian_application_id"]
        user.xidian_recommend_flag = candidate["xidian_recommend_flag"]
        user.xidian_application_status = candidate["xidian_application_status"]
        user.family_name = candidate["family_name"]
        user.given_name = candidate["given_name"]
        user.gender = candidate["gender"]
        user.nationality = candidate["nationality"]
        user.passport_expiry = candidate["passport_expiry"]
        user.birthday = candidate["birthday"]
        user.remark = candidate["remark"]
        user.source = candidate["source"]
        user.imported_at = now

        if face_image_oss_key:
            user.face_image_oss_key = face_image_oss_key
            user.face_enrolled_at = now
            user.face_image_source = "manual_upload"

        db.commit()
        db.refresh(user)

        report.update(
            {
                "action": "created" if created else "updated",
                "id": user.id,
                "status": user.status,
                "face_image_oss_key": user.face_image_oss_key or "",
                "login_account": user.passport_no,
            }
        )
        return report
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Create or update one candidate in users. Login account is passport number; "
            "default password is uppercase passport number plus 2026."
        )
    )
    parser.add_argument("--name", required=True, help="Candidate real name.")
    parser.add_argument("--passport-no", required=True, help="Passport number used as login account.")
    parser.add_argument("--email", required=True, help="Candidate email / registered account.")
    parser.add_argument("--photo", default="", help="Local face photo path to upload to OSS.")
    parser.add_argument("--password", default="", help="Optional initial password. Defaults to PASSPORT2026.")
    parser.add_argument("--application-no", default="", help="Application number, e.g. 20260700015.")
    parser.add_argument("--application-id", default="", help="External application id.")
    parser.add_argument("--family-name", default="")
    parser.add_argument("--given-name", default="")
    parser.add_argument("--gender", default="")
    parser.add_argument("--nationality", default="")
    parser.add_argument("--passport-expiry", default="", help="YYYY-MM-DD.")
    parser.add_argument("--birthday", default="", help="YYYY-MM-DD.")
    parser.add_argument("--recommend-flag", default="")
    parser.add_argument("--application-status", default="")
    parser.add_argument("--status", default="active", help="active or disabled.")
    parser.add_argument("--remark", default="")
    parser.add_argument("--source", default="manual_single_import")
    parser.add_argument("--dry-run", action="store_true", help="Validate arguments only; do not write DB or OSS.")
    parser.add_argument("--report", default="", help="Optional JSON report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = upsert_manual_candidate(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
