import asyncio
import json
import time
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
import jwt

from core.config import (
    ALGORITHM,
    FACE_CONSENT_VERSION,
    FACE_IMAGE_MAX_BYTES,
    FACE_IMAGE_SIGN_EXPIRE_SECONDS,
    FACE_OSS_BUCKET_NAME,
    FACE_OSS_ENDPOINT,
    FACE_LIVENESS_REQUIRED,
    FACE_VERIFY_ENABLED,
    FACE_VERIFY_TTL_SECONDS,
    PROCTORING_ENABLED,
    PROCTORING_IDENTITY_RECHECK_INTERVAL_SECONDS,
    PROCTORING_MIN_INTERVAL_SECONDS,
    PROCTORING_STORE_RAW_RESULT,
    SECRET_KEY,
)
from core.database import InterviewRecord, ProctoringEvent, SessionLocal, User
from core.face_policy import aggregate_proctoring_flags, compare_passed, max_risk, risk_for_flags
from core.face_service import compare_face, detect_living_face, monitor_examination
from core.llm_agent import session_exists, update_session_runtime
from core.oss_utils import sign_oss_url, upload_bytes_to_oss
from core.redis_utils import json_get, json_set, redis_key

router = APIRouter()

_local_face_verified = {}
_local_proctoring_limit = {}
_local_identity_recheck_limit = {}
_local_last_proctoring_flags = {}


def get_authenticated_user_email(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, {"status": "error", "message": "请先登录"}
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub"), None
    except jwt.ExpiredSignatureError:
        return None, {"status": "error", "message": "身份凭证已过期，请重新登录"}
    except jwt.InvalidTokenError:
        return None, {"status": "error", "message": "非法的身份凭证"}


def face_verified_key(email: str) -> str:
    return redis_key("face_verified", (email or "").lower())


def get_face_verified(email: str) -> dict | None:
    payload = json_get(face_verified_key(email))
    if payload:
        return payload
    item = _local_face_verified.get((email or "").lower())
    if item and item.get("expires_at", 0) > time.time():
        return item
    return None


def set_face_verified(email: str, payload: dict) -> None:
    payload = {**payload, "expires_at": time.time() + FACE_VERIFY_TTL_SECONDS}
    if json_set(face_verified_key(email), payload, FACE_VERIFY_TTL_SECONDS):
        return
    _local_face_verified[(email or "").lower()] = payload


async def read_image_file(image: UploadFile) -> tuple[bytes, dict | None]:
    content_type = (image.content_type or "").lower()
    if not content_type.startswith("image/"):
        return b"", {"status": "error", "code": "invalid_image_type", "message": "请上传图片文件"}
    data = await image.read()
    if not data:
        return b"", {"status": "error", "code": "empty_image", "message": "图片为空"}
    if len(data) > FACE_IMAGE_MAX_BYTES:
        return b"", {"status": "error", "code": "image_too_large", "message": "图片过大，请重新拍摄"}
    return data, None


def parse_client_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def upload_face_image(data: bytes, oss_key: str) -> str:
    upload_bytes_to_oss(data, oss_key, True, endpoint=FACE_OSS_ENDPOINT, bucket_name=FACE_OSS_BUCKET_NAME)
    return face_image_url_from_db(oss_key)


def face_image_url_from_db(value: str) -> str:
    value = (value or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    if not value:
        return ""
    return sign_oss_url(
        value,
        FACE_IMAGE_SIGN_EXPIRE_SECONDS,
        endpoint=FACE_OSS_ENDPOINT,
        bucket_name=FACE_OSS_BUCKET_NAME,
    )


def should_run_identity_recheck(limit_key: str, flags: list[str], previous_flags: list[str], now: float) -> tuple[bool, str]:
    trigger_flags = {"multiple_faces", "multiple_persons"}
    if set(flags or []) & trigger_flags:
        _local_identity_recheck_limit[limit_key] = now
        return True, "proctoring_anomaly"

    away_flags = {"no_face", "person_absent"}
    if (set(previous_flags or []) & away_flags) and not (set(flags or []) & away_flags):
        _local_identity_recheck_limit[limit_key] = now
        return True, "face_returned"

    last_time = _local_identity_recheck_limit.get(limit_key, 0)
    if not last_time:
        _local_identity_recheck_limit[limit_key] = now
        return False, ""
    if now - last_time >= PROCTORING_IDENTITY_RECHECK_INTERVAL_SECONDS:
        _local_identity_recheck_limit[limit_key] = now
        return True, "scheduled"
    return False, ""


def proctoring_suggestion(flags: list[str]) -> str:
    flag_set = set(flags or [])
    if "identity_recheck_failed" in flag_set:
        return "身份复核异常，请保持本人正对摄像头"
    if "multiple_faces" in flag_set:
        return "检测到多张人脸，请确保画面中只有本人"
    if "multiple_persons" in flag_set:
        return "检测到多人入镜，请保持本人单独出现在画面中"
    if "no_face" in flag_set:
        return "未检测到人脸，请回到摄像头画面中央"
    if "person_absent" in flag_set:
        return "检测到人员离席，请回到画面中继续面试"
    if "face_not_centered" in flag_set:
        return "人脸偏离画面，请将面部移到摄像头中央"
    if "head_down" in flag_set:
        return "检测到低头，请尽量正视摄像头"
    if "head_turned" in flag_set:
        return "检测到转头，请保持正对摄像头"
    return ""


@router.get("/status")
async def face_status(request: Request):
    email, auth_error = get_authenticated_user_email(request)
    if auth_error:
        return auth_error

    if not FACE_VERIFY_ENABLED:
        return {
            "status": "success",
            "enrolled": True,
            "identity_document_uploaded": True,
            "identity_doc_uploaded_at": "",
            "identity_doc_type": "",
            "face_enrolled_at": "",
            "consent_version": FACE_CONSENT_VERSION,
            "need_reenroll": False,
            "precheck_valid": True,
            "disabled": True,
        }

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        enrolled = bool(user and user.face_image_oss_key)
        identity_document_uploaded = enrolled
        return {
            "status": "success",
            "enrolled": enrolled,
            "identity_document_uploaded": identity_document_uploaded,
            "identity_doc_uploaded_at": user.face_enrolled_at.isoformat() if user and user.face_enrolled_at else "",
            "identity_doc_type": "face_photo" if enrolled else "",
            "face_enrolled_at": user.face_enrolled_at.isoformat() if user and user.face_enrolled_at else "",
            "consent_version": FACE_CONSENT_VERSION,
            "need_reenroll": False,
            "precheck_valid": bool(get_face_verified(email)),
        }
    finally:
        db.close()


@router.post("/identity-document")
async def identity_document_upload(
    request: Request,
    image: UploadFile = File(...),
    document_type: str = Form("passport_or_id"),
    consent_version: str = Form(""),
):
    email, auth_error = get_authenticated_user_email(request)
    if auth_error:
        return auth_error
    data, error = await read_image_file(image)
    if error:
        return error
    if not FACE_VERIFY_ENABLED:
        return {
            "status": "success",
            "message": "identity document uploaded",
            "identity_document_uploaded": True,
            "disabled": True,
        }

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return {"status": "error", "code": "user_not_found", "message": "user not found"}
        oss_key = f"face/identity_doc/{user.id}/{uuid4().hex}.jpg"
        await asyncio.to_thread(upload_face_image, data, oss_key)
        now = datetime.now()
        user.face_image_oss_key = oss_key
        user.face_enrolled_at = now
        db.commit()
        return {
            "status": "success",
            "message": "identity document uploaded",
            "identity_document_uploaded": True,
            "identity_doc_uploaded_at": now.isoformat(timespec="seconds"),
            "identity_doc_type": "face_photo",
        }
    except Exception as exc:
        db.rollback()
        return {"status": "error", "code": "identity_document_upload_failed", "message": str(exc)}
    finally:
        db.close()


@router.post("/enroll")
async def face_enroll(request: Request, image: UploadFile = File(...), consent_version: str = Form("")):
    email, auth_error = get_authenticated_user_email(request)
    if auth_error:
        return auth_error
    data, error = await read_image_file(image)
    if error:
        return error
    if not FACE_VERIFY_ENABLED:
        return {"status": "success", "message": "face enrolled", "enrolled": True, "disabled": True}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return {"status": "error", "code": "user_not_found", "message": "用户不存在"}
        oss_key = f"face/enroll/{user.id}/{uuid4().hex}.jpg"
        signed_url = await asyncio.to_thread(upload_face_image, data, oss_key)
        if FACE_LIVENESS_REQUIRED:
            living = await asyncio.to_thread(detect_living_face, signed_url)
            if not living.get("passed"):
                return {"status": "error", "code": "liveness_failed", "message": "未通过活体检测，请重新拍摄"}
        now = datetime.now()
        user.face_image_oss_key = oss_key
        user.face_enrolled_at = now
        db.commit()
        return {"status": "success", "message": "face enrolled", "enrolled": True}
    except Exception as exc:
        db.rollback()
        return {"status": "error", "code": "face_enroll_failed", "message": str(exc)}
    finally:
        db.close()


@router.post("/precheck")
async def face_precheck(request: Request, image: UploadFile = File(...)):
    email, auth_error = get_authenticated_user_email(request)
    if auth_error:
        return auth_error
    data, error = await read_image_file(image)
    if error:
        return error
    if not FACE_VERIFY_ENABLED:
        set_face_verified(email, {
            "verified": True,
            "user_email": email,
            "score": None,
            "snapshot_oss_key": "",
            "verified_at": datetime.now().isoformat(timespec="seconds"),
        })
        return {
            "status": "success",
            "verified": True,
            "liveness_passed": True,
            "compare_score": None,
            "expires_in": FACE_VERIFY_TTL_SECONDS,
            "disabled": True,
        }

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return {"status": "error", "code": "user_not_found", "message": "user not found", "verified": False}
        base_oss_key = user.face_image_oss_key
        if not base_oss_key:
            return {
                "status": "error",
                "code": "identity_document_required",
                "message": "Please upload your passport or identity document before face verification.",
                "verified": False,
            }
        oss_key = f"face/precheck/{user.id}/{uuid4().hex}.jpg"
        current_url = await asyncio.to_thread(upload_face_image, data, oss_key)
        enrolled_url = face_image_url_from_db(base_oss_key)
        if not enrolled_url:
            return {"status": "error", "code": "identity_document_unavailable", "message": "Face photo is unavailable.", "verified": False}

        living = await asyncio.to_thread(detect_living_face, current_url)
        if FACE_LIVENESS_REQUIRED and not living.get("passed"):
            return {"status": "error", "code": "liveness_failed", "message": "活体检测未通过，请调整光线后重试", "verified": False}

        compared = await asyncio.to_thread(compare_face, enrolled_url, current_url)
        score = compared.get("score")
        verified = compare_passed(score)
        if not verified:
            return {
                "status": "error",
                "code": "face_verify_failed",
                "message": "身份核验未通过，请正对摄像头后重试",
                "verified": False,
                "liveness_passed": bool(living.get("passed")),
                "compare_score": score,
            }

        payload = {
            "verified": True,
            "user_email": email,
            "score": score,
            "snapshot_oss_key": oss_key,
            "identity_doc_oss_key": base_oss_key,
            "identity_source": "face_photo",
            "liveness_passed": bool(living.get("passed")),
            "verified_at": datetime.now().isoformat(timespec="seconds"),
        }
        set_face_verified(email, payload)
        return {
            "status": "success",
            "verified": True,
            "liveness_passed": bool(living.get("passed")),
            "compare_score": score,
            "expires_in": FACE_VERIFY_TTL_SECONDS,
        }
    except Exception as exc:
        return {"status": "error", "code": "face_precheck_failed", "message": str(exc), "verified": False}
    finally:
        db.close()


@router.post("/proctoring")
async def face_proctoring(
    request: Request,
    session_id: str = Form(...),
    image: UploadFile = File(...),
    client_captured_at: str = Form(""),
):
    email, auth_error = get_authenticated_user_email(request)
    if auth_error:
        return auth_error
    if not PROCTORING_ENABLED:
        return {"status": "success", "risk_level": "none", "flags": []}
    if not session_exists(session_id):
        return {"status": "error", "code": "session_not_found", "message": "面试会话不存在或已结束"}

    limit_key = f"{email}:{session_id}"
    now = time.time()
    last_time = _local_proctoring_limit.get(limit_key, 0)
    if now - last_time < PROCTORING_MIN_INTERVAL_SECONDS:
        return {"status": "error", "code": "too_frequent", "message": "监考截帧过于频繁"}
    _local_proctoring_limit[limit_key] = now

    data, error = await read_image_file(image)
    if error:
        return error

    try:
        oss_key = f"face/proctoring/{session_id}/{int(now)}_{uuid4().hex}.jpg"
        signed_url = await asyncio.to_thread(upload_face_image, data, oss_key)
        result = await asyncio.to_thread(monitor_examination, signed_url)
        flags = result.get("flags") or []
        identity_recheck = {"checked": False}
        previous_flags = _local_last_proctoring_flags.get(limit_key, [])
        run_recheck, recheck_reason = should_run_identity_recheck(limit_key, flags, previous_flags, now)
        _local_last_proctoring_flags[limit_key] = flags
        if run_recheck:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.email == email).first()
                base_oss_key = user.face_image_oss_key if user else ""
            finally:
                db.close()

            if base_oss_key:
                base_url = face_image_url_from_db(base_oss_key)
                if base_url:
                    compared = await asyncio.to_thread(compare_face, base_url, signed_url)
                    score = compared.get("score")
                    passed = compare_passed(score)
                    identity_recheck = {"checked": True, "passed": passed, "score": score, "reason": recheck_reason}
                    if not passed:
                        flags = [*flags, "identity_recheck_failed"]
                else:
                    identity_recheck = {"checked": True, "passed": False, "reason": recheck_reason, "error": "identity document unavailable"}
                    flags = [*flags, "identity_recheck_failed"]
            else:
                identity_recheck = {"checked": True, "passed": False, "reason": recheck_reason, "error": "identity document missing"}
                flags = [*flags, "identity_recheck_failed"]

        risk_level = risk_for_flags(flags)
        raw_json = json.dumps(result.get("raw") or {}, ensure_ascii=False) if PROCTORING_STORE_RAW_RESULT else ""

        db = SessionLocal()
        try:
            event_flags = flags or ["normal"]
            for flag in event_flags:
                db.add(
                    ProctoringEvent(
                        session_id=session_id,
                        user_email=email,
                        event_type=flag,
                        risk_level=risk_level,
                        image_oss_key=oss_key if flags else "",
                        raw_result_json=raw_json,
                        client_captured_at=parse_client_time(client_captured_at),
                    )
                )
            if identity_recheck.get("checked") and identity_recheck.get("passed"):
                db.add(
                    ProctoringEvent(
                        session_id=session_id,
                        user_email=email,
                        event_type="identity_recheck_passed",
                        risk_level="none",
                        image_oss_key=oss_key,
                        raw_result_json=json.dumps(identity_recheck, ensure_ascii=False),
                        client_captured_at=parse_client_time(client_captured_at),
                    )
                )
            record = db.query(InterviewRecord).filter_by(session_id=session_id).first()
            if record:
                record.proctoring_risk_level = max_risk(record.proctoring_risk_level or "none", risk_level)
                record.proctoring_flags_json = aggregate_proctoring_flags(record.proctoring_flags_json, flags)
            db.commit()
        finally:
            db.close()

        update_session_runtime(session_id, proctoring={"risk_level": risk_level, "flags": flags})
        suggestion = proctoring_suggestion(flags)
        return {
            "status": "success",
            "risk_level": risk_level,
            "flags": flags,
            "suggestion": suggestion,
            "identity_recheck": identity_recheck,
        }
    except Exception as exc:
        return {"status": "error", "code": "proctoring_failed", "message": str(exc)}
