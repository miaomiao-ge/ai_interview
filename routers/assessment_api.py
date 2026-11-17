import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

from core.assessment import load_instrument
from core.database import SessionLocal, User
from core.psych_assessment_service import (
    latest_for_user,
    save_draft,
    skip_assessment,
    submit_assessment,
)
from routers.user_api import get_authenticated_user_identity

router = APIRouter()

LOCALE_KEYS = {"zh": "zh", "zh-cn": "zh", "en": "en", "en-us": "en", "ru": "ru"}


def build_instrument_view(locale: str = "zh") -> dict:
    key = LOCALE_KEYS.get((locale or "zh").lower(), "zh")
    instrument = load_instrument()
    return {
        "instrument": instrument["instrument"],
        "version": instrument["version"],
        "scale": [
            {"value": point["value"], "text": point.get(key) or point["zh"]}
            for point in instrument["scale"]
        ],
        "items": [
            {"no": item["no"], "text": item.get(key) or item["zh"]}
            for item in instrument["items"]
        ],
    }


class AnswersRequest(BaseModel):
    answers: dict = {}
    consent_version: str = "v1"


class SkipRequest(BaseModel):
    reason: str = ""


def _current_user(request: Request):
    identity, auth_error = get_authenticated_user_identity(request)
    if auth_error:
        return None, auth_error
    if not identity:
        return None, {"status": "error", "code": "login_required", "message": "请先登录"}
    db = SessionLocal()
    user = db.query(User).filter(User.id == identity["id"]).first()
    if not user:
        db.close()
        return None, {"status": "error", "code": "user_not_found", "message": "账号不存在"}
    return (db, user), None


@router.get("/bsi53")
async def instrument(request: Request, locale: str = "zh"):
    context, error = _current_user(request)
    if error:
        return error
    db, user = context
    try:
        record = latest_for_user(db, user.id)
        view = build_instrument_view(locale)
        view["assessment_status"] = record.status if record else "NONE"
        view["answers"] = {}
        if record and record.status == "draft" and record.answers_json:
            view["answers"] = json.loads(record.answers_json)
        return {"status": "success", **view}
    finally:
        db.close()


@router.put("/draft")
async def draft(request: Request, body: AnswersRequest):
    context, error = _current_user(request)
    if error:
        return error
    db, user = context
    try:
        save_draft(db, user, body.answers, body.consent_version)
        return {"status": "success"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        db.close()


@router.post("/submit")
async def submit(request: Request, body: AnswersRequest):
    context, error = _current_user(request)
    if error:
        return error
    db, user = context
    try:
        record = submit_assessment(db, user, body.answers, body.consent_version)
        return {
            "status": "success",
            "risk_level": record.risk_level,
            "risk_items": json.loads(record.risk_items_json or "[]"),
        }
    except ValueError as exc:
        return {"status": "error", "code": "invalid_answers", "message": str(exc)}
    finally:
        db.close()


@router.post("/skip")
async def skip(request: Request, body: SkipRequest):
    context, error = _current_user(request)
    if error:
        return error
    db, user = context
    try:
        skip_assessment(db, user, body.reason)
        return {"status": "success"}
    finally:
        db.close()


@router.get("/result")
async def result(request: Request):
    context, error = _current_user(request)
    if error:
        return error
    db, user = context
    try:
        record = latest_for_user(db, user.id)
        if not record:
            return {"status": "success", "assessment_status": "NONE"}
        return {
            "status": "success",
            "assessment_status": record.status,
            "risk_level": record.risk_level,
            "submitted_at": record.submitted_at.isoformat() if record.submitted_at else None,
        }
    finally:
        db.close()
