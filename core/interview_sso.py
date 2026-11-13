"""One-time tickets issued by the international student platform."""
import base64
import hashlib
import hmac
import json
import time

from core.config import INTERVIEW_SSO_SECRET, INTERVIEW_SSO_TTL_SECONDS
from core.redis_utils import get_redis_client, redis_key


class SSOTicketError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_sso_ticket(ticket: str) -> dict:
    if not INTERVIEW_SSO_SECRET:
        raise SSOTicketError("sso_not_configured")
    if not ticket or len(ticket) > 4096 or "." not in ticket:
        raise SSOTicketError("sso_invalid")
    body, signature = ticket.split(".", 1)
    expected = hmac.new(
        INTERVIEW_SSO_SECRET.encode("utf-8"), body.encode("ascii", "ignore"), hashlib.sha256
    ).digest()
    try:
        provided = _b64decode(signature)
    except (ValueError, TypeError):
        raise SSOTicketError("sso_invalid")
    if not hmac.compare_digest(expected, provided):
        raise SSOTicketError("sso_invalid")
    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, TypeError, json.JSONDecodeError):
        raise SSOTicketError("sso_invalid")
    if not isinstance(payload, dict) or payload.get("aud") != "ai-interview":
        raise SSOTicketError("sso_invalid")
    try:
        expires_at = int(payload.get("exp") or 0)
    except (TypeError, ValueError):
        raise SSOTicketError("sso_invalid")
    now = int(time.time())
    if expires_at < now:
        raise SSOTicketError("sso_expired")
    if expires_at > now + max(INTERVIEW_SSO_TTL_SECONDS * 2, 300):
        raise SSOTicketError("sso_invalid")
    passport_no = str(payload.get("passport_no") or "").strip().upper()
    nonce = str(payload.get("nonce") or "").strip()
    if not passport_no or not nonce or len(nonce) > 128:
        raise SSOTicketError("sso_invalid")
    client = get_redis_client()
    if client is not None:
        key = redis_key("sso", "nonce", nonce)
        if not client.set(key, "1", nx=True, ex=max(INTERVIEW_SSO_TTL_SECONDS * 2, 300)):
            raise SSOTicketError("sso_reused")
    return payload
