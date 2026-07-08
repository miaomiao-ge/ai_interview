import hashlib
import time
import random
import json
import jwt
import os
import asyncio
import threading
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.database import SessionLocal, User
from core.email_utils import send_verification_email
from core.llm_agent import (
    clear_interview_session,
    create_interview_session,
    generate_interview_response,
    session_exists,
    update_session_runtime,
)
from core.interview_job_service import enqueue_interview_processing, get_interview_status
from core.tts_utils import generate_tts_audio
from core.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_DAYS,
    ASR_DEBUG_LOG,
    ASR_FILE_MAX_CONCURRENT,
    LLM_MAX_CONCURRENT,
    TTS_MAX_CONCURRENT,
    get_aliyun_asr_appkey,
    get_aliyun_asr_start_options,
    get_aliyun_token,
)
from core.config import (
    LOGIN_LIMIT_PER_WINDOW,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    OTP_EMAIL_LIMIT_PER_WINDOW,
    OTP_IP_LIMIT_PER_WINDOW,
    OTP_RATE_LIMIT_WINDOW_SECONDS,
    OTP_TTL_SECONDS,
)
from core.config import ANSWER_AUDIO_UPLOAD_MAX_BYTES, MEDIA_UPLOAD_MAX_BYTES, OSS_PATH_PREFIX
from core.config import FACE_VERIFY_ENABLED
from core.concurrency_guard import (
    release_active_asr,
    release_active_session,
    try_register_active_asr,
    try_register_active_session,
)
from core.oss_utils import upload_to_oss
from core.redis_utils import (
    delete_key,
    fixed_window_current_count,
    fixed_window_increment,
    fixed_window_rate_limited,
    json_get,
    json_set,
    redis_key,
)
from routers.face_api import get_face_verified

router = APIRouter()

otp_store = {}
_local_rate_limits = {}
_llm_semaphore = asyncio.Semaphore(max(1, LLM_MAX_CONCURRENT))
_tts_semaphore = asyncio.Semaphore(max(1, TTS_MAX_CONCURRENT))
_asr_file_semaphore = asyncio.Semaphore(max(1, ASR_FILE_MAX_CONCURRENT))


async def run_llm_task(func, *args):
    async with _llm_semaphore:
        return await asyncio.to_thread(func, *args)


async def run_tts_task(func, *args):
    async with _tts_semaphore:
        return await asyncio.to_thread(func, *args)


async def run_asr_file_task(func, *args):
    async with _asr_file_semaphore:
        return await asyncio.to_thread(func, *args)


def capacity_error_response(kind: str, active_count: int, limit: int) -> dict:
    return {
        "status": "error",
        "code": "capacity_limit",
        "kind": kind,
        "message": f"系统当前并发已满，请稍后再试（{active_count}/{limit}）。",
        "active_count": active_count,
        "limit": limit,
    }


def get_client_ip(request: Optional[Request]) -> str:
    client = getattr(request, "client", None)
    return getattr(client, "host", "") or "unknown"


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_login_identifier(value: str) -> str:
    return (value or "").strip()


def normalize_passport_no(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def user_identity_value(user: User) -> str:
    return normalize_passport_no(getattr(user, "passport_no", "")) or str(getattr(user, "id", "") or "")


def serialize_user_identity(user: User) -> dict:
    return {
        "id": getattr(user, "id", None),
        "subject": user_identity_value(user),
        "email": getattr(user, "email", "") or "",
        "passport_no": normalize_passport_no(getattr(user, "passport_no", "")),
        "real_name": getattr(user, "real_name", "") or "",
    }


def find_user_by_login_identifier(db, identifier: str):
    passport_no = normalize_passport_no(identifier)
    if not passport_no:
        return None
    return db.query(User).filter(User.passport_no == passport_no).first()


def find_user_from_token_payload(db, payload: dict):
    user_id = payload.get("user_id")
    if user_id is None:
        subject = str(payload.get("sub") or "")
        if subject.isdigit():
            user_id = int(subject)
    if user_id is not None:
        try:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user:
                return user
        except (TypeError, ValueError):
            pass

    passport_no = normalize_passport_no(payload.get("passport_no") or payload.get("sub") or "")
    if passport_no:
        user = db.query(User).filter(User.passport_no == passport_no).first()
        if user:
            return user

    legacy_email = normalize_email(payload.get("email") or payload.get("sub") or "")
    if legacy_email and "@" in legacy_email:
        return db.query(User).filter(User.email == legacy_email).order_by(User.id.asc()).first()
    return None


def _otp_key(email: str, purpose: str) -> str:
    return redis_key("otp", purpose, normalize_email(email))


def _local_otp_key(email: str, purpose: str) -> str:
    return f"{purpose}:{normalize_email(email)}"


def store_otp(email: str, purpose: str, code: str) -> None:
    payload = {"code": code, "expire_at": time.time() + OTP_TTL_SECONDS}
    if json_set(_otp_key(email, purpose), payload, OTP_TTL_SECONDS):
        return
    otp_store[_local_otp_key(email, purpose)] = payload


def read_otp(email: str, purpose: str) -> Optional[dict]:
    payload = json_get(_otp_key(email, purpose))
    if payload:
        return payload
    return otp_store.get(_local_otp_key(email, purpose))


def delete_otp(email: str, purpose: str) -> None:
    delete_key(_otp_key(email, purpose))
    otp_store.pop(_local_otp_key(email, purpose), None)


def local_fixed_window_rate_limited(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    now = time.time()
    item = _local_rate_limits.get(key)
    if not item or now >= item["reset_at"]:
        item = {"count": 0, "reset_at": now + window_seconds}
    item["count"] += 1
    _local_rate_limits[key] = item
    return item["count"] > limit, item["count"]


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    limited, count = fixed_window_rate_limited(key, limit, window_seconds)
    if count:
        return limited
    limited, _ = local_fixed_window_rate_limited(key, limit, window_seconds)
    return limited


def local_rate_limit_count(key: str) -> int:
    now = time.time()
    item = _local_rate_limits.get(key)
    if not item or now >= item["reset_at"]:
        _local_rate_limits.pop(key, None)
        return 0
    return int(item.get("count") or 0)


def local_rate_limit_increment(key: str, window_seconds: int) -> int:
    now = time.time()
    item = _local_rate_limits.get(key)
    if not item or now >= item["reset_at"]:
        item = {"count": 0, "reset_at": now + window_seconds}
    item["count"] += 1
    _local_rate_limits[key] = item
    return int(item["count"])


def is_login_failure_limited(key: str, limit: int) -> bool:
    redis_count = fixed_window_current_count(key)
    if redis_count:
        return redis_count >= limit
    return local_rate_limit_count(key) >= limit


def record_login_failure(key: str, window_seconds: int) -> None:
    if fixed_window_increment(key, window_seconds):
        return
    local_rate_limit_increment(key, window_seconds)


def clear_rate_limit(key: str) -> None:
    delete_key(key)
    _local_rate_limits.pop(key, None)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

class SendEmailCodeRequest(BaseModel):
    email: str
    purpose: str

class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    code: str

class LoginRequest(BaseModel):
    email: str = ""
    passport_no: str = ""
    password: str

class ResetPasswordRequest(BaseModel):
    email: str
    new_password: str
    code: str

# ✨ 新增
class StartInterviewRequest(BaseModel):
    language: str = "zh"


class CancelInterviewRequest(BaseModel):
    session_id: str


class EndInterviewRequest(BaseModel):
    session_id: str


class SubmitAnswerRequest(BaseModel):
    session_id: str
    text: str = ""


def get_authenticated_user_identity(request: Request) -> Tuple[Optional[dict], Optional[dict]]:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, None

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        db = SessionLocal()
        try:
            user = find_user_from_token_payload(db, payload)
            if not user:
                return None, {"status": "error", "message": "账号不存在，请重新登录"}
            return serialize_user_identity(user), None
        finally:
            db.close()
    except jwt.ExpiredSignatureError:
        return None, {"status": "error", "message": "身份凭证已过期，请重新登录"}
    except jwt.InvalidTokenError:
        return None, {"status": "error", "message": "非法的身份凭证"}


def get_authenticated_user_email(request: Request) -> Tuple[Optional[str], Optional[dict]]:
    identity, auth_error = get_authenticated_user_identity(request)
    if auth_error:
        return None, auth_error
    if not identity:
        return "anonymous@unknown.com", None
    return identity["subject"], None


def _safe_media_extension(ext: str, content_type: str) -> str:
    normalized = (ext or "").strip().lower().lstrip(".")
    if normalized in {"webm", "mkv", "mp4"}:
        return normalized
    if "mp4" in content_type:
        return "mp4"
    if "matroska" in content_type or "mkv" in content_type:
        return "mkv"
    return "webm"


def _media_upload_path(session_id: str, ext: str) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(base_dir, "media", "records", "audio_video")
    os.makedirs(upload_dir, exist_ok=True)
    return os.path.join(upload_dir, f"{session_id}.{ext}")


def _media_oss_key(session_id: str, ext: str) -> str:
    return f"{OSS_PATH_PREFIX}/records/audio_video/{session_id}.{ext}".strip("/")


def _store_uploaded_media(session_id: str, ext: str, bytes_count: int, oss_key: str, oss_url: str) -> dict:
    media_info = {
        "url": oss_url,
        "oss_key": oss_key,
        "ext": ext,
        "bytes": bytes_count,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    update_session_runtime(session_id, status="media_uploaded", media={"av": media_info})
    return media_info


class RealtimeASRSession:
    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        language: str,
        loop: asyncio.AbstractEventLoop,
        audio_device: str = "",
    ):
        self.websocket = websocket
        self.session_id = session_id
        self.language = language
        self.audio_device = (audio_device or "").strip()[:120]
        self.loop = loop
        self.transcriber = None
        self.final_text_parts = []
        self.latest_partial_text = ""
        self.last_logged_partial_text = ""
        self.received_audio_bytes = 0
        self.received_audio_chunks = 0
        self.closed = False
        self.done = threading.Event()

    def log(self, event: str, detail: str = "") -> None:
        if not ASR_DEBUG_LOG:
            return
        session_tag = self.session_id[:8] if self.session_id else "unknown"
        suffix = f" {detail}" if detail else ""
        print(f"[ASR][{session_tag}][{event}]{suffix}", flush=True)

    def _send_json_threadsafe(self, payload: dict) -> None:
        if self.closed:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.websocket.send_json(payload), self.loop)
        except RuntimeError:
            pass

    def on_start(self, message, *args):
        self.log("ready")
        self._send_json_threadsafe({"type": "asr_ready", "session_id": self.session_id})

    def on_sentence_begin(self, message, *args):
        pass

    def on_result_changed(self, message, *args):
        try:
            text = json.loads(message).get("payload", {}).get("result", "")
        except Exception:
            text = ""
        if text:
            self.latest_partial_text = text
            if text != self.last_logged_partial_text:
                self.last_logged_partial_text = text
                self.log("partial", text)
            self._send_json_threadsafe({"type": "asr_partial", "text": text})

    def on_sentence_end(self, message, *args):
        try:
            text = json.loads(message).get("payload", {}).get("result", "")
        except Exception:
            text = ""
        if text:
            self.final_text_parts.append(text)
            self.latest_partial_text = ""
            self.last_logged_partial_text = ""
            self.log("final", text)
            self._send_json_threadsafe({"type": "asr_final", "text": self.text()})

    def on_error(self, message, *args):
        self.log("error", str(message))
        self._send_json_threadsafe({"type": "asr_error", "message": str(message)})

    def on_close(self, *args):
        self.log("closed")
        self.done.set()

    def start(self) -> None:
        token = get_aliyun_token()
        if not token:
            raise RuntimeError("阿里云 ASR token 获取失败")

        import nls

        self.transcriber = nls.NlsSpeechTranscriber(
            url="wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1",
            appkey=get_aliyun_asr_appkey(self.language),
            token=token,
            on_start=self.on_start,
            on_sentence_begin=self.on_sentence_begin,
            on_result_changed=self.on_result_changed,
            on_sentence_end=self.on_sentence_end,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.transcriber.start(**get_aliyun_asr_start_options())
        if self.audio_device:
            self.log("audio_device", self.audio_device)

    def send_audio(self, pcm_data: bytes) -> None:
        if self.transcriber and pcm_data:
            self.received_audio_chunks += 1
            self.received_audio_bytes += len(pcm_data)
            self.transcriber.send_audio(pcm_data)

    def text(self) -> str:
        return "".join(self.final_text_parts).strip() or self.latest_partial_text.strip()

    def finish_text(self, timeout_seconds: float = 1.5) -> str:
        if self.transcriber:
            try:
                self.transcriber.stop()
            except Exception:
                pass
            self.done.wait(timeout=timeout_seconds)
            self.transcriber = None
        self.log(
            "finish",
            f"chunks={self.received_audio_chunks} bytes={self.received_audio_bytes} text={self.text() or '<empty>'}",
        )
        return self.text()

    def stop(self) -> None:
        self.closed = True
        if self.transcriber:
            try:
                self.transcriber.stop()
            except Exception:
                pass
            self.transcriber = None


def _answer_audio_upload_path(session_id: str, ext: str) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(base_dir, "media", "answers")
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{session_id}_{int(time.time() * 1000)}.{ext}"
    return os.path.join(upload_dir, filename)


async def save_request_body_to_file(request: Request, filepath: str, max_bytes: int) -> int:
    tmp_filepath = f"{filepath}.uploading"
    received = 0
    with open(tmp_filepath, "wb") as file:
        async for chunk in request.stream():
            if not chunk:
                continue
            received += len(chunk)
            if received > max_bytes:
                file.close()
                try:
                    os.remove(tmp_filepath)
                except OSError:
                    pass
                raise ValueError("上传文件过大")
            file.write(chunk)
    os.replace(tmp_filepath, filepath)
    return received


def choose_better_asr_text(primary_text: str, fallback_text: str, primary_source: str):
    primary = (primary_text or "").strip()
    fallback = (fallback_text or "").strip()
    if not primary:
        return fallback, "fallback_text" if fallback else primary_source
    if fallback and len(primary) <= 6 and len(fallback) >= len(primary) + 3:
        return fallback, "fallback_text"
    if fallback and len(fallback) >= 12 and len(primary) < len(fallback) * 0.6:
        return fallback, "fallback_text"
    return primary, primary_source


@router.post("/send_email_code")
async def send_email_code(req: SendEmailCodeRequest, request: Request = None):
    req.email = normalize_email(req.email)
    if req.purpose not in {"register", "forgot"}:
        return {"status": "error", "message": "验证码用途不合法"}

    client_ip = get_client_ip(request)
    email_limit_key = redis_key("rate_limit", "otp_email", req.purpose, req.email)
    ip_limit_key = redis_key("rate_limit", "otp_ip", req.purpose, client_ip)
    if is_rate_limited(email_limit_key, OTP_EMAIL_LIMIT_PER_WINDOW, OTP_RATE_LIMIT_WINDOW_SECONDS):
        return {"status": "error", "message": "验证码请求过于频繁，请稍后再试。"}
    if is_rate_limited(ip_limit_key, OTP_IP_LIMIT_PER_WINDOW, OTP_RATE_LIMIT_WINDOW_SECONDS):
        return {"status": "error", "message": "当前网络请求验证码过于频繁，请稍后再试。"}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == req.email).first()
        if req.purpose == "register" and user:
            return {"status": "error", "message": "该邮箱已被注册，请直接登录！"}
        if req.purpose == "forgot" and not user:
            return {"status": "error", "message": "该邮箱尚未注册！"}
    finally:
        db.close()

    code = str(random.randint(100000, 999999))

    if send_verification_email(req.email, code, req.purpose):
        store_otp(req.email, req.purpose, code)
        return {"status": "success", "message": "验证码已发送至您的邮箱，请查收！"}
    else:
        return {"status": "error", "message": "邮件发送失败，请检查系统配置。"}

@router.post("/register")
async def register(req: RegisterRequest):
    req.email = normalize_email(req.email)
    otp = read_otp(req.email, "register")
    if not otp or time.time() > otp["expire_at"] or otp["code"] != req.code:
        return {"status": "error", "message": "验证码无效或已过期！"}

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == req.email).first():
            return {"status": "error", "message": "该邮箱已被注册！"}

        new_user = User(
            email=req.email,
            real_name=req.username,
            password_hash=hash_password(req.password),
            status="active",
            source="self_register",
        )
        db.add(new_user)
        db.commit()
        delete_otp(req.email, "register")
        return {"status": "success", "message": "注册成功，请登录！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@router.post("/reset_password")
async def reset_password(req: ResetPasswordRequest):
    req.email = normalize_email(req.email)
    otp = read_otp(req.email, "forgot")
    if not otp or time.time() > otp["expire_at"] or otp["code"] != req.code:
        return {"status": "error", "message": "验证码无效或已过期！"}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == req.email).first()
        if not user:
            return {"status": "error", "message": "该邮箱尚未注册！"}

        user.password_hash = hash_password(req.new_password)
        db.commit()
        delete_otp(req.email, "forgot")
        return {"status": "success", "message": "密码重置成功，请重新登录！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@router.post("/login")
async def login(req: LoginRequest, request: Request = None):
    login_id = normalize_login_identifier(req.passport_no or req.email)
    login_key = normalize_passport_no(login_id) or login_id
    client_ip = get_client_ip(request)
    email_limit_key = redis_key("rate_limit", "login_passport", login_key)
    ip_limit_key = redis_key("rate_limit", "login_ip", client_ip)
    if is_login_failure_limited(email_limit_key, LOGIN_LIMIT_PER_WINDOW):
        return {"status": "error", "message": "登录尝试过于频繁，请稍后再试。"}
    if is_login_failure_limited(ip_limit_key, LOGIN_LIMIT_PER_WINDOW * 3):
        return {"status": "error", "message": "当前网络登录尝试过于频繁，请稍后再试。"}

    db = SessionLocal()
    try:
        user = find_user_by_login_identifier(db, login_id)
        if not user or user.password_hash != hash_password(req.password):
            record_login_failure(email_limit_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
            record_login_failure(ip_limit_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
            return {"status": "error", "message": "护照号或密码错误！"}

        if getattr(user, "status", "active") != "active":
            record_login_failure(email_limit_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
            record_login_failure(ip_limit_key, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
            return {"status": "error", "code": "user_disabled", "message": "账号已停用，请联系管理员"}

        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        identity = serialize_user_identity(user)
        payload = {
            "sub": str(user.id),
            "user_id": user.id,
            "email": user.email or "",
            "username": user.real_name,
            "passport_no": identity["passport_no"],
            "exp": expire
        }
        real_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        clear_rate_limit(email_limit_key)
        clear_rate_limit(ip_limit_key)

        return {
            "status": "success",
            "token": real_token,
            "username": user.real_name,
            "email": user.email or "",
            "passport_no": identity["passport_no"],
        }
    finally:
        db.close()

# 接收前端传来的语言
@router.post("/start_interview")
async def start_interview(req: StartInterviewRequest, request: Request):
    identity, auth_error = get_authenticated_user_identity(request)
    if auth_error:
        return auth_error
    if not identity:
        return {"status": "error", "code": "login_required", "message": "请先登录"}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == identity["id"]).first()
        if not user:
            return {"status": "error", "code": "user_not_found", "message": "账号不存在，请联系管理员"}
        if getattr(user, "status", "active") != "active":
            return {"status": "error", "code": "user_disabled", "message": "账号已停用，请联系管理员"}
        has_face_image = bool(user.face_image_oss_key)
    finally:
        db.close()

    user_subject = identity["subject"]
    face_verified = get_face_verified(user_subject)
    if FACE_VERIFY_ENABLED and not has_face_image:
        return {
            "status": "error",
            "code": "identity_document_required",
            "message": "未找到预置人脸照片，请联系管理员",
        }
    if FACE_VERIFY_ENABLED and not face_verified:
        return {
            "status": "error",
            "code": "face_precheck_required",
            "message": "请先完成人脸身份核验",
        }

    session_id = uuid4().hex[:8]
    admission = await asyncio.to_thread(try_register_active_session, session_id)
    if not admission.allowed:
        return capacity_error_response("active_interviews", admission.active_count, admission.limit)

    try:
        session_id, first_question = await run_llm_task(create_interview_session, req.language, session_id)
        update_session_runtime(
            session_id,
            user_email=user_subject,
            face_verify=face_verified or {"verified": False},
        )

        # 为首个开场问题生成阿里云 TTS
        spoken_text = first_question
        try:
            parsed = json.loads(first_question.replace('```json', '').replace('```', '').strip())
            spoken_text = parsed.get('spoken', first_question)
        except:
            pass

        audio_url = await run_tts_task(generate_tts_audio, spoken_text, session_id, req.language)

        # 将 audio_url 连同题目和 session_id 一起下发
        return {"status": "success", "session_id": session_id, "first_question": first_question, "audio_url": audio_url}
    except Exception as e:
        clear_interview_session(session_id)
        await asyncio.to_thread(release_active_session, session_id)
        return {"status": "error", "message": str(e)}


@router.post("/cancel_interview")
async def cancel_interview(req: CancelInterviewRequest):
    session_id = (req.session_id or "").strip()
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}

    clear_interview_session(session_id)
    return {"status": "success", "message": "面试会话已取消"}


@router.post("/submit_answer")
async def submit_answer(req: SubmitAnswerRequest):
    session_id = (req.session_id or "").strip()
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}
    if not session_exists(session_id):
        return {"status": "error", "message": "面试会话不存在或已失效"}

    answer_text = (req.text or "").strip() or "【候选人未作答 / No Answer】"
    update_session_runtime(session_id, status="llm_processing")
    reply_data = await run_llm_task(generate_interview_response, session_id, answer_text)

    spoken_text = reply_data["text"]
    try:
        parsed = json.loads(reply_data["text"].replace("```json", "").replace("```", "").strip())
        spoken_text = parsed.get("spoken", spoken_text)
    except Exception:
        pass

    update_session_runtime(session_id, status="tts_processing")
    audio_url = await run_tts_task(generate_tts_audio, spoken_text, session_id)
    reply_data["audio_url"] = audio_url
    update_session_runtime(session_id, status="ending" if reply_data.get("is_end") else "waiting_next_answer")

    return {
        "status": "success",
        "type": "reply",
        "text": reply_data["text"],
        "audio_url": audio_url,
        "is_end": reply_data["is_end"],
    }


@router.post("/submit_answer_media")
async def submit_answer_media(
    session_id: str,
    request: Request,
    ext: str = "webm",
    language: str = "zh",
    fallback_text: str = "",
):
    session_id = (session_id or "").strip()
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}
    if not session_exists(session_id):
        return {"status": "error", "message": "面试会话不存在或已失效"}

    content_type = request.headers.get("content-type", "")
    safe_ext = _safe_media_extension(ext, content_type)
    filepath = _answer_audio_upload_path(session_id, safe_ext)

    try:
        await save_request_body_to_file(request, filepath, ANSWER_AUDIO_UPLOAD_MAX_BYTES)
        update_session_runtime(session_id, status="asr_processing")
        from core.asr_file import transcribe_media_file

        answer_text = await run_asr_file_task(transcribe_media_file, filepath, language)
        asr_source = "server_file_asr"
        if ASR_DEBUG_LOG:
            print(
                f"[ASR][{session_id[:8]}][file_result] text={answer_text or '<empty>'} fallback={fallback_text or '<empty>'}",
                flush=True,
            )
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        print(f"⚠️ 服务端 ASR 识别失败，使用前端兜底文本: {exc}")
        answer_text = (fallback_text or "").strip()
        asr_source = "fallback_text"
    finally:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            pass

    answer_text, asr_source = choose_better_asr_text(answer_text, fallback_text, asr_source)
    if ASR_DEBUG_LOG:
        print(f"[ASR][{session_id[:8]}][chosen] source={asr_source} text={answer_text or '<empty>'}", flush=True)

    if not answer_text:
        answer_text = "【候选人未作答 / No Answer】"

    reply = await submit_answer(SubmitAnswerRequest(session_id=session_id, text=answer_text))
    if isinstance(reply, dict):
        reply["recognized_text"] = answer_text
        reply["asr_source"] = asr_source
    return reply


@router.websocket("/ws/asr")
async def realtime_asr_ws(websocket: WebSocket, session_id: str, language: str = "zh", audio_device: str = ""):
    session_id = (session_id or "").strip()
    await websocket.accept()
    if not session_id:
        await websocket.send_json({"type": "error", "message": "缺少 session_id"})
        await websocket.close()
        return
    if not session_exists(session_id):
        await websocket.send_json({"type": "error", "message": "面试会话不存在或已失效"})
        await websocket.close()
        return

    connection_id = f"{session_id}:{uuid4().hex[:8]}"
    admission = await asyncio.to_thread(try_register_active_asr, connection_id)
    if not admission.allowed:
        await websocket.send_json(
            {
                "type": "error",
                "code": "capacity_limit",
                "message": f"实时语音识别连接已满，请稍后再试（{admission.active_count}/{admission.limit}）。",
                "active_count": admission.active_count,
                "limit": admission.limit,
            }
        )
        await websocket.close()
        return

    loop = asyncio.get_running_loop()
    asr_session = RealtimeASRSession(websocket, session_id, language, loop, audio_device)
    fallback_text = ""
    finish_mode = "reply"
    if ASR_DEBUG_LOG:
        device_suffix = f" audio_device={audio_device}" if audio_device else ""
        print(f"[ASR][{session_id[:8]}][ws_connect] language={language}{device_suffix}", flush=True)

    try:
        update_session_runtime(session_id, status="asr_processing")
        await asyncio.to_thread(asr_session.start)

        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return

            pcm_data = message.get("bytes")
            if pcm_data is not None:
                await asyncio.to_thread(asr_session.send_audio, pcm_data)
                continue

            text_message = message.get("text")
            if not text_message:
                continue
            try:
                payload = json.loads(text_message)
            except json.JSONDecodeError:
                payload = {"action": text_message}

            if payload.get("fallback_text"):
                fallback_text = str(payload.get("fallback_text") or "").strip()
            action = payload.get("action")
            if action in {"finish_answer", "finish_asr"}:
                finish_mode = "asr_only" if action == "finish_asr" else "reply"
                if ASR_DEBUG_LOG:
                    print(
                        f"[ASR][{session_id[:8]}][finish_signal] mode={finish_mode} fallback_len={len(fallback_text)}",
                        flush=True,
                    )
                break

        final_answer = await asyncio.to_thread(asr_session.finish_text)
        final_answer = final_answer or fallback_text or "【候选人未作答 / No Answer】"
        if ASR_DEBUG_LOG:
            source = "realtime_ws_asr" if asr_session.text() else "fallback_text"
            print(f"[ASR][{session_id[:8]}][answer] source={source} text={final_answer}", flush=True)

        if finish_mode == "asr_only":
            await websocket.send_json(
                {
                    "type": "asr_done",
                    "status": "success",
                    "recognized_text": final_answer,
                    "asr_source": "realtime_ws_asr" if asr_session.text() else "fallback_text",
                }
            )
            await websocket.close()
            return

        update_session_runtime(session_id, status="llm_processing")
        if ASR_DEBUG_LOG:
            print(f"[ASR][{session_id[:8]}][llm_input] text={final_answer}", flush=True)
        reply_data = await run_llm_task(generate_interview_response, session_id, final_answer)
        spoken_text = reply_data["text"]
        try:
            parsed = json.loads(reply_data["text"].replace("```json", "").replace("```", "").strip())
            spoken_text = parsed.get("spoken", spoken_text)
        except Exception:
            pass

        update_session_runtime(session_id, status="tts_processing")
        audio_url = await run_tts_task(generate_tts_audio, spoken_text, session_id, language)
        reply_data["audio_url"] = audio_url
        update_session_runtime(session_id, status="ending" if reply_data.get("is_end") else "waiting_next_answer")
        if ASR_DEBUG_LOG:
            print(
                f"[ASR][{session_id[:8]}][reply_ready] is_end={reply_data.get('is_end')} audio_url={audio_url}",
                flush=True,
            )

        await websocket.send_json(
            {
                "type": "reply",
                "status": "success",
                "text": reply_data["text"],
                "audio_url": audio_url,
                "is_end": reply_data["is_end"],
                "recognized_text": final_answer,
                "asr_source": "realtime_ws_asr" if asr_session.text() else "fallback_text",
            }
        )
        await websocket.close()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close()
        except Exception:
            pass
    finally:
        asr_session.stop()
        await asyncio.to_thread(release_active_asr, connection_id)


@router.post("/upload_media")
async def upload_media(session_id: str, request: Request, ext: str = "mkv"):
    session_id = (session_id or "").strip()
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}
    if not session_exists(session_id):
        status = get_interview_status(session_id)
        if status.get("status") == "not_found":
            return {"status": "error", "message": "面试会话不存在或已失效"}

    content_type = request.headers.get("content-type", "")
    safe_ext = _safe_media_extension(ext, content_type)
    filepath = _media_upload_path(session_id, safe_ext)
    oss_key = _media_oss_key(session_id, safe_ext)

    try:
        received = await save_request_body_to_file(request, filepath, MEDIA_UPLOAD_MAX_BYTES)
        oss_url = await asyncio.to_thread(upload_to_oss, filepath, oss_key, True)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        return {"status": "error", "message": f"OSS upload failed: {exc}"}
    finally:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
    media_info = _store_uploaded_media(session_id, safe_ext, received, oss_key, oss_url)
    return {
        "status": "success",
        "message": "媒体文件上传完成",
        "session_id": session_id,
        "bytes": received,
        "url": oss_url,
        "oss_key": oss_key,
        "media": media_info,
    }


@router.websocket("/ws/upload_media")
async def upload_media_ws(websocket: WebSocket, session_id: str, ext: str = "mkv"):
    session_id = (session_id or "").strip()
    await websocket.accept()
    if not session_id:
        await websocket.send_json({"status": "error", "message": "缺少 session_id"})
        await websocket.close()
        return
    if not session_exists(session_id):
        await websocket.send_json({"status": "error", "message": "面试会话不存在或已失效"})
        await websocket.close()
        return

    safe_ext = _safe_media_extension(ext, "")
    filepath = _media_upload_path(session_id, safe_ext)
    tmp_filepath = f"{filepath}.uploading"
    oss_key = _media_oss_key(session_id, safe_ext)
    received = 0
    completed = False

    try:
        with open(tmp_filepath, "wb") as file:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    chunk = message["bytes"]
                    received += len(chunk)
                    if received > MEDIA_UPLOAD_MAX_BYTES:
                        await websocket.send_json({"status": "error", "message": "媒体文件过大"})
                        await websocket.close()
                        return
                    file.write(chunk)
                    await websocket.send_json({"status": "receiving", "bytes": received})
                    continue

                text_message = message.get("text")
                if text_message:
                    try:
                        payload = json.loads(text_message)
                    except json.JSONDecodeError:
                        payload = {"type": text_message}
                    if payload.get("type") == "complete":
                        completed = True
                        break

        if completed:
            os.replace(tmp_filepath, filepath)
            try:
                oss_url = await asyncio.to_thread(upload_to_oss, filepath, oss_key, True)
                media_info = _store_uploaded_media(session_id, safe_ext, received, oss_key, oss_url)
            except Exception as exc:
                await websocket.send_json({"status": "error", "message": f"OSS upload failed: {exc}"})
                await websocket.close()
                return
            await websocket.send_json(
                {
                    "status": "success",
                    "message": "媒体文件上传完成",
                    "session_id": session_id,
                    "bytes": received,
                    "url": oss_url,
                    "oss_key": oss_key,
                    "media": media_info,
                }
            )
        await websocket.close()
    except WebSocketDisconnect:
        pass
    finally:
        if not completed and os.path.exists(tmp_filepath):
            try:
                os.remove(tmp_filepath)
            except OSError:
                pass
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass


@router.post("/end_interview")
async def end_interview(req: EndInterviewRequest, request: Request):
    session_id = (req.session_id or "").strip()
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}

    user_email, auth_error = get_authenticated_user_email(request)
    if auth_error:
        return auth_error

    return enqueue_interview_processing(session_id, user_email)


@router.get("/interview_status")
async def interview_status(session_id: str):
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}
    return get_interview_status(session_id)


@router.get("/get_evaluation")
async def get_evaluation(session_id: str, request: Request):
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}

    current_status = get_interview_status(session_id)
    if current_status.get("status") not in {"not_found", "pending"}:
        return current_status

    user_email, auth_error = get_authenticated_user_email(request)
    if auth_error:
        return auth_error
    return enqueue_interview_processing(session_id, user_email)
