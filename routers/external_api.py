import hmac
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Form, Header, HTTPException, Query
from sqlalchemy import or_

from core.config import (
    ALGORITHM,
    EXTERNAL_RESULT_API_KEY,
    EXTERNAL_RESULT_APP_KEY,
    EXTERNAL_RESULT_APP_SECRET,
    EXTERNAL_RESULT_TOKEN_EXPIRE_SECONDS,
    SECRET_KEY,
)
from core.database import InterviewRecord, SessionLocal, User


router = APIRouter()
TOKEN_SCOPE = "external_interview_results"


def _bearer_token(authorization: str | None) -> str:
    value = (authorization or "").strip()
    if not value:
        return ""
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return value


def verify_external_api_key(
    authorization: str | None = None,
    x_external_api_key: str | None = None,
) -> None:
    expected = EXTERNAL_RESULT_API_KEY
    if not expected:
        raise HTTPException(status_code=503, detail="external result api key is not configured")

    provided = (x_external_api_key or "").strip() or _bearer_token(authorization)
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid external api key")


def pdf_success(data_object: Any, message: str = "请求成功!") -> dict:
    return {
        "result": "1",
        "message": message,
        "dataObject": data_object,
        "valid": True,
    }


def pdf_error(message: str) -> dict:
    return {
        "result": "0",
        "message": message,
        "dataObject": None,
        "valid": False,
    }


def _external_app_key() -> str:
    return EXTERNAL_RESULT_APP_KEY or EXTERNAL_RESULT_API_KEY


def _external_app_secret() -> str:
    return EXTERNAL_RESULT_APP_SECRET or EXTERNAL_RESULT_API_KEY


def create_external_token(app_key: str) -> str:
    expires_at = datetime.utcnow() + timedelta(seconds=EXTERNAL_RESULT_TOKEN_EXPIRE_SECONDS)
    payload = {
        "scope": TOKEN_SCOPE,
        "appKey": app_key,
        "exp": expires_at,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_external_token(token: str) -> tuple[bool, str]:
    if not token:
        return False, "token不能为空"
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return False, "token已过期，请重新获取"
    except jwt.InvalidTokenError:
        return False, "token无效"

    expected_app_key = _external_app_key()
    if payload.get("scope") != TOKEN_SCOPE:
        return False, "token用途不正确"
    if expected_app_key and payload.get("appKey") != expected_app_key:
        return False, "token对应的appKey不正确"
    return True, ""


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return ""


def _json_object(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list_or_dict(value: str | None) -> Any:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, (dict, list)) else {}


def normalize_passport_no(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def parse_form_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def interview_result_payload(record: InterviewRecord) -> dict:
    structured = _json_object(getattr(record, "evaluation_result_json", "") or "")
    return {
        "recordId": getattr(record, "id", None),
        "sessionId": getattr(record, "session_id", "") or "",
        "status": getattr(record, "evaluate_status", "") or "",
        "archiveStatus": getattr(record, "archive_status", "") or "",
        "archiveError": getattr(record, "archive_error", "") or "",
        "reviewStatus": getattr(record, "review_status", "") or "",
        "reviewRemark": getattr(record, "review_remark", "") or "",
        "report": getattr(record, "evaluation_result", "") or "",
        "structured": structured,
        "totalScore": structured.get("total_score"),
        "dimensionScores": structured.get("dimension_scores", []),
        "summary": structured.get("summary", ""),
        "strengths": structured.get("strengths", []),
        "improvements": structured.get("improvements", []),
        "chatHistory": getattr(record, "chat_history", "") or "",
        "faceVerification": {
            "status": getattr(record, "face_verify_status", "") or "",
            "score": getattr(record, "face_verify_score", None),
            "verifiedAt": _iso(getattr(record, "face_verify_at", None)),
            "snapshotOssKey": getattr(record, "face_verify_snapshot_oss_key", "") or "",
            "identityDocOssKey": getattr(record, "identity_doc_oss_key", "") or "",
        },
        "proctoring": {
            "riskLevel": getattr(record, "proctoring_risk_level", "") or "",
            "flags": _json_list_or_dict(getattr(record, "proctoring_flags_json", "") or ""),
        },
        "media": {
            "audioPath": getattr(record, "audio_path", "") or "",
            "videoPath": getattr(record, "video_path", "") or "",
            "avPath": getattr(record, "av_path", "") or "",
        },
        "timestamps": {
            "submittedAt": _iso(getattr(record, "submitted_at", None)),
            "completedAt": _iso(getattr(record, "completed_at", None)),
            "processingStartedAt": _iso(getattr(record, "processing_started_at", None)),
            "processingFinishedAt": _iso(getattr(record, "processing_finished_at", None)),
            "createdAt": _iso(getattr(record, "created_at", None)),
        },
    }


def serialize_result_row(user: User, record: InterviewRecord) -> dict:
    return {
        "name": getattr(user, "real_name", "") or "",
        "familyName": getattr(user, "family_name", "") or "",
        "givenName": getattr(user, "given_name", "") or "",
        "id": getattr(user, "xidian_application_id", "") or "",
        "applicationNo": getattr(user, "xidian_application_no", "") or "",
        "flag": getattr(user, "xidian_recommend_flag", "") or "",
        "passportNumber": getattr(user, "passport_no", "") or "",
        "email": getattr(user, "email", "") or "",
        "interviewResult": interview_result_payload(record),
    }


def collect_interview_result_rows(
    db,
    *,
    year: str = "",
    application_id: str = "",
    application_no: str = "",
    application_ids: list[str] | None = None,
    application_nos: list[str] | None = None,
    passport_no: str = "",
    include_incomplete: bool = False,
    latest_only: bool = True,
    max_rows: int = 5000,
) -> list[dict]:
    query = (
        db.query(User, InterviewRecord)
        .join(
            InterviewRecord,
            or_(
                InterviewRecord.user_email == User.passport_no,
                InterviewRecord.user_email == User.email,
            ),
        )
        .order_by(
            InterviewRecord.completed_at.desc(),
            InterviewRecord.created_at.desc(),
            InterviewRecord.id.desc(),
        )
    )

    clean_year = str(year or "").strip()
    if clean_year:
        query = query.filter(User.xidian_application_no.like(f"{clean_year}%"))
    if application_id:
        query = query.filter(User.xidian_application_id == application_id.strip())
    if application_no:
        query = query.filter(User.xidian_application_no == application_no.strip())
    if application_ids:
        query = query.filter(User.xidian_application_id.in_(application_ids))
    if application_nos:
        query = query.filter(User.xidian_application_no.in_(application_nos))
    if passport_no:
        query = query.filter(User.passport_no == normalize_passport_no(passport_no))
    if not include_incomplete:
        query = query.filter(InterviewRecord.evaluate_status == "success")

    rows = query.limit(max_rows).all()
    data = []
    seen_user_ids = set()
    for user, record in rows:
        if latest_only:
            user_id = getattr(user, "id", None)
            if user_id in seen_user_ids:
                continue
            seen_user_ids.add(user_id)
        data.append(serialize_result_row(user, record))
    return data


@router.get("/interviewResult/getToken")
async def get_external_result_token(
    appKey: str = Query(""),
    appSecret: str = Query(""),
):
    expected_key = _external_app_key()
    expected_secret = _external_app_secret()
    if not expected_key or not expected_secret:
        return pdf_error("服务端未配置EXTERNAL_RESULT_APP_KEY/EXTERNAL_RESULT_APP_SECRET")
    if not hmac.compare_digest((appKey or "").strip(), expected_key):
        return pdf_error("appKey不正确")
    if not hmac.compare_digest((appSecret or "").strip(), expected_secret):
        return pdf_error("appSecret不正确")
    return pdf_success(create_external_token(expected_key), "token生成成功!")


@router.post("/interviewResult/getApplicationInfoBatch")
async def get_application_interview_result_batch(
    token: str = Form(""),
    year: str = Form(""),
    pageNum: int = Form(1),
    pageSize: int = Form(100),
    applicationNos: str = Form(""),
    ids: str = Form(""),
    includeIncomplete: str = Form("false"),
):
    token_ok, token_error = verify_external_token(token)
    if not token_ok:
        return pdf_error(token_error)
    clean_year = str(year or "").strip()
    if not clean_year:
        return pdf_error("year不能为空")
    if pageNum < 1:
        return pdf_error("pageNum必须大于等于1")
    if pageSize < 1 or pageSize > 100:
        return pdf_error("pageSize必须在1到100之间")

    db = SessionLocal()
    try:
        all_rows = collect_interview_result_rows(
            db,
            year=clean_year,
            application_ids=split_csv(ids),
            application_nos=split_csv(applicationNos),
            include_incomplete=parse_form_bool(includeIncomplete),
            latest_only=True,
        )
        start = (pageNum - 1) * pageSize
        page_rows = all_rows[start : start + pageSize]
        return pdf_success(
            {
                "pageNum": pageNum,
                "pageSize": pageSize,
                "totalCount": len(all_rows),
                "year": clean_year,
                "data": page_rows,
            }
        )
    finally:
        db.close()


@router.get("/interview-results")
async def get_interview_results(
    application_id: str = Query("", alias="id"),
    application_no: str = Query("", alias="applicationNo"),
    passport_no: str = Query("", alias="passportNo"),
    include_incomplete: bool = Query(False, alias="includeIncomplete"),
    latest_only: bool = Query(True, alias="latestOnly"),
    limit: int = Query(100, ge=1, le=1000),
    authorization: str | None = Header(None),
    x_external_api_key: str | None = Header(None, alias="X-External-Api-Key"),
):
    verify_external_api_key(authorization=authorization, x_external_api_key=x_external_api_key)

    db = SessionLocal()
    try:
        data = collect_interview_result_rows(
            db,
            application_id=application_id,
            application_no=application_no,
            passport_no=passport_no,
            include_incomplete=include_incomplete,
            latest_only=latest_only,
            max_rows=limit if not latest_only else min(limit * 5, 1000),
        )[:limit]

        return {"status": "success", "count": len(data), "data": data}
    finally:
        db.close()
