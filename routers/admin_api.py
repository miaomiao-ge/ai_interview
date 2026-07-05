import hashlib
import hmac
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import jwt
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from core.config import (
    ADMIN_LOGIN_LIMIT_PER_WINDOW,
    FACE_IMAGE_SIGN_EXPIRE_SECONDS,
    FACE_OSS_BUCKET_NAME,
    FACE_OSS_ENDPOINT,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    ALGORITHM,
    SECRET_KEY,
)
from core.database import (
    AdminActionLog,
    AdminLoginRecord,
    AdminUser,
    InterviewRecord,
    PromptConfig,
    ProctoringEvent,
    QuestionBank,
    SessionLocal,
)
from core.redis_utils import (
    delete_key,
    fixed_window_current_count,
    fixed_window_increment,
    fixed_window_rate_limited,
    redis_key,
)

router = APIRouter()

ADMIN_ROLES = {"super_admin", "admin"}
ADMIN_STATUS_ACTIVE = "active"
ADMIN_STATUS_DISABLED = "disabled"
_local_admin_rate_limits = {}


def hash_admin_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def build_admin_token_signature(stored_password: str) -> str:
    return hash_admin_password("{0}:{1}".format(SECRET_KEY, stored_password or ""))


def is_sha256_hash(value: str) -> bool:
    if not value or len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value.lower())


def verify_admin_password(input_password: str, stored_password: str) -> bool:
    if not stored_password:
        return False
    if is_sha256_hash(stored_password):
        return hmac.compare_digest(hash_admin_password(input_password), stored_password)
    return hmac.compare_digest(input_password, stored_password)


def get_client_ip(request: Request) -> str:
    client = getattr(request, "client", None)
    return getattr(client, "host", "") or ""


def local_fixed_window_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    now = datetime.utcnow().timestamp()
    item = _local_admin_rate_limits.get(key)
    if not item or now >= item["reset_at"]:
        item = {"count": 0, "reset_at": now + window_seconds}
    item["count"] += 1
    _local_admin_rate_limits[key] = item
    return item["count"] > limit


def is_admin_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    limited, count = fixed_window_rate_limited(key, limit, window_seconds)
    if count:
        return limited
    return local_fixed_window_rate_limited(key, limit, window_seconds)


def local_admin_rate_limit_count(key: str) -> int:
    now = datetime.utcnow().timestamp()
    item = _local_admin_rate_limits.get(key)
    if not item or now >= item["reset_at"]:
        _local_admin_rate_limits.pop(key, None)
        return 0
    return int(item.get("count") or 0)


def local_admin_rate_limit_increment(key: str, window_seconds: int) -> int:
    now = datetime.utcnow().timestamp()
    item = _local_admin_rate_limits.get(key)
    if not item or now >= item["reset_at"]:
        item = {"count": 0, "reset_at": now + window_seconds}
    item["count"] += 1
    _local_admin_rate_limits[key] = item
    return int(item["count"])


def is_admin_login_failure_limited(key: str, limit: int) -> bool:
    redis_count = fixed_window_current_count(key)
    if redis_count:
        return redis_count >= limit
    return local_admin_rate_limit_count(key) >= limit


def record_admin_login_failure(key: str, window_seconds: int) -> None:
    if fixed_window_increment(key, window_seconds):
        return
    local_admin_rate_limit_increment(key, window_seconds)


def clear_admin_rate_limit(key: str) -> None:
    delete_key(key)
    _local_admin_rate_limits.pop(key, None)


def normalize_admin_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None
    normalized = email.strip()
    return normalized or None


def is_admin_login_allowed(admin_user: Any) -> bool:
    return bool(admin_user and getattr(admin_user, "status", ADMIN_STATUS_ACTIVE) == ADMIN_STATUS_ACTIVE)


def has_super_admin_privilege(profile: Dict[str, Any]) -> bool:
    return profile.get("role") == "super_admin"


def can_toggle_admin_status(admins: List[Any], target_admin_id: int, next_status: str) -> bool:
    if next_status != ADMIN_STATUS_DISABLED:
        return True

    active_super_admins = [
        item
        for item in admins
        if getattr(item, "role", "") == "super_admin"
        and getattr(item, "status", ADMIN_STATUS_ACTIVE) == ADMIN_STATUS_ACTIVE
    ]
    if len(active_super_admins) == 1 and getattr(active_super_admins[0], "id", None) == target_admin_id:
        return False
    return True


def create_action_log(
    db: Any,
    operator: Optional[Dict[str, Any]],
    action: str,
    target: Optional[Any] = None,
    result: str = "success",
    detail: str = "",
) -> None:
    db.add(
        AdminActionLog(
            admin_id=operator.get("admin_id") if operator else None,
            username_snapshot=operator.get("username", "") if operator else "",
            action=action,
            target_admin_id=getattr(target, "id", None),
            target_username=getattr(target, "username", ""),
            result=result,
            detail=detail,
        )
    )


def serialize_admin(admin: Any) -> Dict[str, Any]:
    last_login_at = getattr(admin, "last_login_at", None)
    created_at = getattr(admin, "created_at", None)
    return {
        "id": getattr(admin, "id", None),
        "username": getattr(admin, "username", ""),
        "display_name": getattr(admin, "display_name", "") or "",
        "email": getattr(admin, "email", None) or "",
        "role": getattr(admin, "role", "admin"),
        "status": getattr(admin, "status", ADMIN_STATUS_ACTIVE),
        "last_login_at": last_login_at.strftime("%Y-%m-%d %H:%M:%S") if last_login_at else "",
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "",
        "created_by": getattr(admin, "created_by", None),
    }


def serialize_login_record(record: Any) -> Dict[str, Any]:
    created_at = getattr(record, "created_at", None)
    return {
        "id": getattr(record, "id", None),
        "username": getattr(record, "username", ""),
        "role": getattr(record, "role", ""),
        "login_status": getattr(record, "login_status", ""),
        "client_ip": getattr(record, "client_ip", "") or "",
        "message": getattr(record, "message", "") or "",
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "",
    }


def serialize_action_log(record: Any) -> Dict[str, Any]:
    created_at = getattr(record, "created_at", None)
    return {
        "id": getattr(record, "id", None),
        "admin_id": getattr(record, "admin_id", None),
        "username_snapshot": getattr(record, "username_snapshot", "") or "",
        "action": getattr(record, "action", "") or "",
        "target_admin_id": getattr(record, "target_admin_id", None),
        "target_username": getattr(record, "target_username", "") or "",
        "result": getattr(record, "result", "") or "",
        "detail": getattr(record, "detail", "") or "",
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "",
    }


def parse_json_dict(value: str | None) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def sign_face_preview_url(oss_key: str | None) -> str:
    if not oss_key:
        return ""
    try:
        from core.oss_utils import sign_oss_url

        return sign_oss_url(
            oss_key,
            FACE_IMAGE_SIGN_EXPIRE_SECONDS,
            endpoint=FACE_OSS_ENDPOINT,
            bucket_name=FACE_OSS_BUCKET_NAME,
        )
    except Exception:
        return ""


def serialize_proctoring_event(event: Any) -> Dict[str, Any]:
    created_at = getattr(event, "created_at", None)
    captured_at = getattr(event, "client_captured_at", None)
    return {
        "id": getattr(event, "id", None),
        "event_type": getattr(event, "event_type", "") or "",
        "risk_level": getattr(event, "risk_level", "") or "",
        "image_oss_key": getattr(event, "image_oss_key", "") or "",
        "image_url": sign_face_preview_url(getattr(event, "image_oss_key", "") or ""),
        "client_captured_at": captured_at.strftime("%Y-%m-%d %H:%M:%S") if captured_at else "",
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "",
    }


def get_admin_by_username(db: Any, username: str) -> Optional[Any]:
    return db.query(AdminUser).filter_by(username=username).first()


def get_admin_by_id(db: Any, admin_id: int) -> Optional[Any]:
    return db.query(AdminUser).filter_by(id=admin_id).first()


def get_all_admin_users(db: Any) -> List[Any]:
    return db.query(AdminUser).order_by(AdminUser.id.desc()).all()


def get_admin_by_email(db: Any, email: Optional[str], exclude_admin_id: Optional[int] = None) -> Optional[Any]:
    if not email:
        return None
    for admin in get_all_admin_users(db):
        if getattr(admin, "email", None) == email and getattr(admin, "id", None) != exclude_admin_id:
            return admin
    return None


def validate_admin_role(role: str) -> bool:
    return role in ADMIN_ROLES


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class ReviewRequest(BaseModel):
    status: str
    remark: str


class QuestionRequest(BaseModel):
    category: str
    content: str


class QuestionBatchDeleteRequest(BaseModel):
    ids: List[int]


class RecordBatchDeleteRequest(BaseModel):
    ids: List[int]


class PromptRequest(BaseModel):
    base_prompt: str
    eval_prompt: str


class AdminCreateRequest(BaseModel):
    username: str
    password: str
    role: str
    display_name: str = ""
    email: str = ""


class AdminUpdateRequest(BaseModel):
    role: str
    display_name: str = ""
    email: str = ""


class AdminPasswordResetRequest(BaseModel):
    new_password: str


class AdminStatusToggleRequest(BaseModel):
    status: str


@router.post("/login")
async def admin_login(req: AdminLoginRequest, request: Request):
    req.username = req.username.strip()
    client_ip = get_client_ip(request)
    username_limit_key = redis_key("rate_limit", "admin_login_user", req.username)
    ip_limit_key = redis_key("rate_limit", "admin_login_ip", client_ip)
    if is_admin_login_failure_limited(username_limit_key, ADMIN_LOGIN_LIMIT_PER_WINDOW):
        return {"status": "error", "message": "管理员登录尝试过于频繁，请稍后再试"}
    if is_admin_login_failure_limited(ip_limit_key, ADMIN_LOGIN_LIMIT_PER_WINDOW * 3):
        return {"status": "error", "message": "当前网络管理员登录尝试过于频繁，请稍后再试"}

    db = SessionLocal()
    try:
        admin = get_admin_by_username(db, req.username)

        if admin and verify_admin_password(req.password, admin.password):
            if not is_admin_login_allowed(admin):
                record_admin_login_failure(username_limit_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
                record_admin_login_failure(ip_limit_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
                db.add(
                    AdminLoginRecord(
                        username=admin.username,
                        role=admin.role,
                        login_status="failed",
                        client_ip=client_ip,
                        message="管理员账号已被禁用",
                    )
                )
                db.commit()
                return {"status": "error", "message": "管理员账号已被禁用"}

            if not is_sha256_hash(admin.password):
                admin.password = hash_admin_password(req.password)
            admin.last_login_at = datetime.utcnow()

            db.add(
                AdminLoginRecord(
                    username=admin.username,
                    role=admin.role,
                    login_status="success",
                    client_ip=client_ip,
                    message="管理员登录成功",
                )
            )
            db.commit()

            expire = datetime.utcnow() + timedelta(days=1)
            payload = {
                "admin_id": admin.id,
                "sub": admin.username,
                "role": admin.role,
                "pwd_sig": build_admin_token_signature(admin.password),
                "exp": expire,
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
            clear_admin_rate_limit(username_limit_key)
            clear_admin_rate_limit(ip_limit_key)
            return {
                "status": "success",
                "token": token,
                "role": admin.role,
                "username": admin.username,
            }

        record_admin_login_failure(username_limit_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        record_admin_login_failure(ip_limit_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        db.add(
            AdminLoginRecord(
                username=req.username,
                role=getattr(admin, "role", ""),
                login_status="failed",
                client_ip=client_ip,
                message="管理员账号或密码错误",
            )
        )
        db.commit()
        return {"status": "error", "message": "管理员账号或密码错误"}
    finally:
        db.close()


def verify_admin_token(auth_header: str, require_super: bool = False) -> Dict[str, Any]:
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供有效的身份令牌")

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录已过期或非法令牌")

    admin_id = payload.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="令牌无效，请重新登录")

    db = SessionLocal()
    try:
        admin_user = get_admin_by_id(db, admin_id)
        if not admin_user:
            raise HTTPException(status_code=401, detail="管理员账号不存在或已被禁用")
        if not is_admin_login_allowed(admin_user):
            raise HTTPException(status_code=401, detail="管理员账号已被禁用")
        stored_password = getattr(admin_user, "password", "") or ""
        if stored_password:
            if payload.get("pwd_sig") != build_admin_token_signature(stored_password):
                raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录")
        if getattr(admin_user, "role", "") not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="权限不足，非管理员账号")
        if require_super and not has_super_admin_privilege({"role": admin_user.role}):
            raise HTTPException(status_code=403, detail="越权操作！只有超级管理员可执行此功能。")
        return {
            "admin_id": admin_user.id,
            "username": admin_user.username,
            "role": admin_user.role,
        }
    finally:
        db.close()


@router.get("/me")
async def get_admin_profile(authorization: str = Header(None)):
    return {"status": "success", "data": verify_admin_token(authorization)}


@router.get("/records")
async def get_admin_records(authorization: str = Header(None)):
    verify_admin_token(authorization)
    db = SessionLocal()
    try:
        records = db.query(InterviewRecord).order_by(InterviewRecord.created_at.desc(), InterviewRecord.id.desc()).all()
        session_ids = [item.session_id for item in records if item.session_id]
        proctoring_events_by_session: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        if session_ids:
            events = (
                db.query(ProctoringEvent)
                .filter(ProctoringEvent.session_id.in_(session_ids))
                .order_by(ProctoringEvent.created_at.desc(), ProctoringEvent.id.desc())
                .all()
            )
            for event in events:
                bucket = proctoring_events_by_session[event.session_id]
                if len(bucket) < 20:
                    bucket.append(serialize_proctoring_event(event))
        data = [
            {
                "id": item.id,
                "user_email": item.user_email,
                "session_id": item.session_id,
                "evaluation_result": item.evaluation_result,
                "chat_history": item.chat_history,
                "evaluation_result_json": item.evaluation_result_json or "",
                "audio_path": item.audio_path,
                "video_path": item.video_path,
                "av_path": item.av_path,
                "archive_status": getattr(item, "archive_status", "") or "",
                "archive_error": getattr(item, "archive_error", "") or "",
                "evaluate_status": getattr(item, "evaluate_status", "") or "",
                "evaluate_error": getattr(item, "evaluate_error", "") or "",
                "processing_started_at": item.processing_started_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(item, "processing_started_at", None) else "",
                "processing_finished_at": item.processing_finished_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(item, "processing_finished_at", None) else "",
                "worker_node_id": getattr(item, "worker_node_id", "") or "",
                "retry_count": getattr(item, "retry_count", 0) or 0,
                "face_verify_status": getattr(item, "face_verify_status", "") or "pending",
                "face_verify_score": getattr(item, "face_verify_score", None),
                "face_verify_at": item.face_verify_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(item, "face_verify_at", None) else "",
                "face_verify_snapshot_oss_key": getattr(item, "face_verify_snapshot_oss_key", "") or "",
                "face_verify_snapshot_url": sign_face_preview_url(getattr(item, "face_verify_snapshot_oss_key", "") or ""),
                "identity_doc_oss_key": getattr(item, "identity_doc_oss_key", "") or "",
                "identity_doc_url": sign_face_preview_url(getattr(item, "identity_doc_oss_key", "") or ""),
                "proctoring_risk_level": getattr(item, "proctoring_risk_level", "") or "none",
                "proctoring_flags": parse_json_dict(getattr(item, "proctoring_flags_json", "") or ""),
                "proctoring_events": proctoring_events_by_session.get(item.session_id, []),
                "proctoring_event_count": len(proctoring_events_by_session.get(item.session_id, [])),
                "created_at": item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
                "review_status": item.review_status or "待复核",
                "review_remark": item.review_remark or "",
            }
            for item in records
        ]
        return {"status": "success", "data": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        db.close()


@router.post("/records/{record_id}/review")
async def update_record_review(record_id: int, req: ReviewRequest, authorization: str = Header(None)):
    verify_admin_token(authorization)
    db = SessionLocal()
    try:
        record = db.query(InterviewRecord).filter_by(id=record_id).first()
        if not record:
            return {"status": "error", "message": "记录不存在"}
        record.review_status = req.status
        record.review_remark = req.remark
        db.commit()
        return {"status": "success", "message": "复核结果已保存"}
    finally:
        db.close()


@router.delete("/records/{record_id}")
async def delete_admin_record(record_id: int, authorization: str = Header(None)):
    operator = verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        record = db.query(InterviewRecord).filter_by(id=record_id).first()
        if not record:
            return {"status": "error", "message": "记录不存在"}
        create_action_log(
            db,
            operator,
            action="delete_interview_record",
            detail=(
                "Deleted interview record "
                f"id={record.id}, session_id={record.session_id or ''}, user_email={record.user_email or ''}"
            ),
        )
        db.delete(record)
        db.commit()
        return {"status": "success", "message": "面试记录已删除"}
    finally:
        db.close()


@router.post("/records/batch_delete")
async def batch_delete_admin_records(req: RecordBatchDeleteRequest, authorization: str = Header(None)):
    operator = verify_admin_token(authorization, require_super=True)
    ids = sorted({int(record_id) for record_id in req.ids if record_id is not None})
    if not ids:
        return {"status": "error", "message": "请先选择要删除的面试记录"}

    db = SessionLocal()
    try:
        query = db.query(InterviewRecord)
        if hasattr(query, "filter"):
            matched_records = query.filter(InterviewRecord.id.in_(ids)).all()
        else:
            matched_records = [item for item in query.all() if getattr(item, "id", None) in ids]
        if not matched_records:
            return {"status": "error", "message": "未找到可删除的面试记录"}

        deleted_ids = []
        details = []
        for record in matched_records:
            deleted_ids.append(record.id)
            details.append(
                f"id={record.id}, session_id={record.session_id or ''}, user_email={record.user_email or ''}"
            )
            db.delete(record)

        create_action_log(
            db,
            operator,
            action="batch_delete_interview_records",
            detail="Deleted interview records: " + "; ".join(details),
        )
        db.commit()
        return {
            "status": "success",
            "message": f"已删除 {len(deleted_ids)} 条面试记录",
            "deleted_ids": deleted_ids,
        }
    finally:
        db.close()


@router.post("/records/{record_id}/retry_archive")
async def retry_record_archive(record_id: int, authorization: str = Header(None)):
    operator = verify_admin_token(authorization, require_super=True)
    from core.interview_job_service import retry_archive_for_record

    result = retry_archive_for_record(record_id)

    db = SessionLocal()
    try:
        target = db.query(InterviewRecord).filter_by(id=record_id).first()
        create_action_log(
            db,
            operator,
            action="retry_archive",
            target=target,
            result="success" if result.get("status") in {"success", "partial_success"} else "failed",
            detail=f"Retry archive result: {result.get('status')} {result.get('archive_error') or result.get('message') or ''}",
        )
        db.commit()
    finally:
        db.close()

    return result


@router.get("/questions")
async def get_questions(authorization: str = Header(None)):
    verify_admin_token(authorization)
    db = SessionLocal()
    try:
        questions = db.query(QuestionBank).order_by(QuestionBank.id.desc()).all()
        return {
            "status": "success",
            "data": [{"id": item.id, "category": item.category, "content": item.content} for item in questions],
        }
    finally:
        db.close()


@router.post("/questions")
async def add_question(req: QuestionRequest, authorization: str = Header(None)):
    verify_admin_token(authorization)
    db = SessionLocal()
    try:
        db.add(QuestionBank(category=req.category, content=req.content))
        db.commit()
        return {"status": "success"}
    finally:
        db.close()


@router.put("/questions/{q_id}")
async def update_question(q_id: int, req: QuestionRequest, authorization: str = Header(None)):
    verify_admin_token(authorization)
    db = SessionLocal()
    try:
        question = db.query(QuestionBank).filter_by(id=q_id).first()
        if not question:
            return {"status": "error", "message": "题目不存在"}
        question.category = req.category
        question.content = req.content
        db.commit()
        return {"status": "success"}
    finally:
        db.close()


@router.delete("/questions/{q_id}")
async def delete_question(q_id: int, authorization: str = Header(None)):
    verify_admin_token(authorization)
    db = SessionLocal()
    try:
        question = db.query(QuestionBank).filter_by(id=q_id).first()
        if not question:
            return {"status": "error", "message": "题目不存在"}
        db.delete(question)
        db.commit()
        return {"status": "success"}
    finally:
        db.close()


@router.post("/questions/batch_delete")
async def batch_delete_questions(req: QuestionBatchDeleteRequest, authorization: str = Header(None)):
    verify_admin_token(authorization)
    ids = sorted({int(qid) for qid in req.ids if qid is not None})
    if not ids:
        return {"status": "error", "message": "请先选择要删除的题目"}

    db = SessionLocal()
    try:
        query = db.query(QuestionBank)
        if hasattr(query, "filter"):
            matched_questions = query.filter(QuestionBank.id.in_(ids)).all()
        else:
            matched_questions = [item for item in query.all() if getattr(item, "id", None) in ids]
        if not matched_questions:
            return {"status": "error", "message": "未找到可删除的题目"}

        for question in matched_questions:
            db.delete(question)
        db.commit()
        return {
            "status": "success",
            "deleted_count": len(matched_questions),
            "message": "批量删除完成",
        }
    finally:
        db.close()


@router.get("/prompts")
async def get_prompts(authorization: str = Header(None)):
    verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        base_prompt = db.query(PromptConfig).filter_by(config_key="base_prompt").first()
        eval_prompt = db.query(PromptConfig).filter_by(config_key="eval_prompt").first()
        return {
            "status": "success",
            "data": {
                "base_prompt": base_prompt.config_value if base_prompt else "",
                "eval_prompt": eval_prompt.config_value if eval_prompt else "",
            },
        }
    finally:
        db.close()


@router.post("/prompts")
async def update_prompts(req: PromptRequest, authorization: str = Header(None)):
    operator = verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        for key, value in [("base_prompt", req.base_prompt), ("eval_prompt", req.eval_prompt)]:
            config = db.query(PromptConfig).filter_by(config_key=key).first()
            if config:
                config.config_value = value
            else:
                db.add(PromptConfig(config_key=key, config_value=value))
        create_action_log(db, operator, action="update_prompts", detail="Updated admin prompt configuration")
        db.commit()
        return {"status": "success", "message": "AI 提示词已实时生效！"}
    finally:
        db.close()


@router.get("/admins")
async def get_admin_users(authorization: str = Header(None)):
    verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        admins = get_all_admin_users(db)
        return {"status": "success", "data": [serialize_admin(item) for item in admins]}
    finally:
        db.close()


@router.post("/admins")
async def create_admin_user(req: AdminCreateRequest, authorization: str = Header(None)):
    operator = verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        username = req.username.strip()
        if not username:
            return {"status": "error", "message": "管理员账号不能为空"}
        if not req.password.strip():
            return {"status": "error", "message": "管理员密码不能为空"}
        if not validate_admin_role(req.role):
            return {"status": "error", "message": "管理员角色不合法"}
        if get_admin_by_username(db, username):
            return {"status": "error", "message": "管理员账号已存在"}

        email = normalize_admin_email(req.email)
        if get_admin_by_email(db, email):
            return {"status": "error", "message": "邮箱已被其他管理员占用"}

        target = AdminUser(
            username=username,
            password=hash_admin_password(req.password),
            role=req.role,
            status=ADMIN_STATUS_ACTIVE,
            display_name=req.display_name.strip() or username,
            email=email,
            last_login_at=None,
            created_by=operator["admin_id"],
        )
        db.add(target)
        create_action_log(db, operator, action="create_admin", target=target, detail="Created admin account")
        db.commit()
        return {"status": "success", "message": "管理员创建成功", "data": serialize_admin(target)}
    finally:
        db.close()


@router.put("/admins/{admin_id}")
async def update_admin_user(admin_id: int, req: AdminUpdateRequest, authorization: str = Header(None)):
    operator = verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        target = get_admin_by_id(db, admin_id)
        if not target:
            return {"status": "error", "message": "管理员不存在"}
        if not validate_admin_role(req.role):
            return {"status": "error", "message": "管理员角色不合法"}

        email = normalize_admin_email(req.email)
        if get_admin_by_email(db, email, exclude_admin_id=admin_id):
            return {"status": "error", "message": "邮箱已被其他管理员占用"}

        if getattr(target, "role", "") == "super_admin" and req.role != "super_admin":
            admins = get_all_admin_users(db)
            active_super_admins = [
                item
                for item in admins
                if getattr(item, "role", "") == "super_admin"
                and getattr(item, "status", ADMIN_STATUS_ACTIVE) == ADMIN_STATUS_ACTIVE
            ]
            if len(active_super_admins) == 1 and getattr(active_super_admins[0], "id", None) == admin_id:
                return {"status": "error", "message": "不能降级最后一个启用中的超级管理员"}

        target.role = req.role
        target.display_name = req.display_name.strip() or target.username
        target.email = email
        create_action_log(db, operator, action="update_admin", target=target, detail="Updated admin profile")
        db.commit()
        return {"status": "success", "message": "管理员信息已更新", "data": serialize_admin(target)}
    finally:
        db.close()


@router.post("/admins/{admin_id}/reset_password")
async def reset_admin_password(
    admin_id: int,
    req: AdminPasswordResetRequest,
    authorization: str = Header(None),
):
    operator = verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        target = get_admin_by_id(db, admin_id)
        if not target:
            return {"status": "error", "message": "管理员不存在"}
        if not req.new_password.strip():
            return {"status": "error", "message": "新密码不能为空"}

        target.password = hash_admin_password(req.new_password)
        create_action_log(db, operator, action="reset_admin_password", target=target, detail="Reset admin password")
        db.commit()
        return {"status": "success", "message": "管理员密码已重置"}
    finally:
        db.close()


@router.post("/admins/{admin_id}/toggle_status")
async def toggle_admin_status(
    admin_id: int,
    req: AdminStatusToggleRequest,
    authorization: str = Header(None),
):
    operator = verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        target = get_admin_by_id(db, admin_id)
        if not target:
            return {"status": "error", "message": "管理员不存在"}
        if req.status not in {ADMIN_STATUS_ACTIVE, ADMIN_STATUS_DISABLED}:
            return {"status": "error", "message": "管理员状态不合法"}

        admins = get_all_admin_users(db)
        if not can_toggle_admin_status(admins, admin_id, req.status):
            return {"status": "error", "message": "不能禁用最后一个启用中的超级管理员"}

        target.status = req.status
        create_action_log(
            db,
            operator,
            action="toggle_admin_status",
            target=target,
            detail="Updated admin status to {0}".format(req.status),
        )
        db.commit()
        return {"status": "success", "message": "管理员状态已更新", "data": serialize_admin(target)}
    finally:
        db.close()


@router.get("/admins/login_records")
async def get_admin_login_records(authorization: str = Header(None)):
    verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        records = db.query(AdminLoginRecord).order_by(AdminLoginRecord.created_at.desc(), AdminLoginRecord.id.desc()).all()
        return {"status": "success", "data": [serialize_login_record(item) for item in records]}
    finally:
        db.close()


@router.get("/admins/action_logs")
async def get_admin_action_logs(authorization: str = Header(None)):
    verify_admin_token(authorization, require_super=True)
    db = SessionLocal()
    try:
        records = db.query(AdminActionLog).order_by(AdminActionLog.created_at.desc(), AdminActionLog.id.desc()).all()
        return {"status": "success", "data": [serialize_action_log(item) for item in records]}
    finally:
        db.close()
