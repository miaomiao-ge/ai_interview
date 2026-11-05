"""Client for the platform account service's internal student endpoint.

Only account metadata and password hashes cross this boundary; plaintext
passwords never leave the AI interview service.
"""
from dataclasses import dataclass

import httpx

from core.config import (
    PLATFORM_ACCOUNT_API_BASE,
    PLATFORM_ACCOUNT_PAGE_SIZE,
    PLATFORM_ACCOUNT_SYNC_TIMEOUT_SECONDS,
    PLATFORM_ACCOUNT_SYNC_TOKEN,
)


class PlatformAccountError(RuntimeError):
    pass


def _headers() -> dict:
    if not PLATFORM_ACCOUNT_SYNC_TOKEN:
        raise PlatformAccountError("未配置 PLATFORM_ACCOUNT_SYNC_TOKEN")
    return {"Authorization": f"Bearer {PLATFORM_ACCOUNT_SYNC_TOKEN}", "Accept": "application/json"}


def _get(path: str, params: dict) -> dict:
    if not PLATFORM_ACCOUNT_API_BASE:
        raise PlatformAccountError("未配置 PLATFORM_ACCOUNT_API_BASE")
    url = f"{PLATFORM_ACCOUNT_API_BASE}{path}"
    timeout = httpx.Timeout(PLATFORM_ACCOUNT_SYNC_TIMEOUT_SECONDS)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.get(url, params=params, headers=_headers())
    except httpx.HTTPError as exc:
        raise PlatformAccountError("平台账号服务连接失败") from exc
    if response.status_code == 401:
        raise PlatformAccountError("平台账号服务拒绝了同步凭证")
    if response.status_code != 200:
        raise PlatformAccountError("平台账号服务返回异常状态")
    try:
        payload = response.json()
    except ValueError as exc:
        raise PlatformAccountError("平台账号服务返回了无效 JSON") from exc
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise PlatformAccountError("平台账号服务返回结构不正确")
    return payload


def fetch_student(account: str) -> dict | None:
    payload = _get("/account/api/internal/students", {"account": account, "page": 1, "page_size": 1})
    students = payload.get("students")
    if not isinstance(students, list):
        raise PlatformAccountError("平台账号服务返回结构不正确")
    return students[0] if students else None


def fetch_student_photo(account: str) -> dict | None:
    """Return {"kind":"oss",...} or {"kind":"bytes","content":...,"extension":...}."""
    if not PLATFORM_ACCOUNT_API_BASE:
        raise PlatformAccountError("未配置 PLATFORM_ACCOUNT_API_BASE")
    url = f"{PLATFORM_ACCOUNT_API_BASE}/account/api/internal/students/photo"
    timeout = httpx.Timeout(PLATFORM_ACCOUNT_SYNC_TIMEOUT_SECONDS)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.get(url, params={"account": account}, headers=_headers())
    except httpx.HTTPError as exc:
        raise PlatformAccountError("平台照片服务连接失败") from exc
    if response.status_code == 404:
        return None
    if response.status_code == 401:
        raise PlatformAccountError("平台账号服务拒绝了同步凭证")
    if response.status_code != 200:
        raise PlatformAccountError("平台照片服务返回异常状态")
    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = response.json()
        except ValueError as exc:
            raise PlatformAccountError("平台照片服务返回了无效 JSON") from exc
        if not isinstance(payload, dict) or payload.get("kind") != "oss" or not payload.get("key"):
            raise PlatformAccountError("平台照片服务返回结构不正确")
        return payload
    if content_type.startswith("image/"):
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
        return {"kind": "bytes", "content": response.content, "extension": extension}
    raise PlatformAccountError("平台照片服务返回了不支持的类型")


def iter_students(limit: int | None = None):
    page = 1
    yielded = 0
    page_size = max(1, min(PLATFORM_ACCOUNT_PAGE_SIZE, 1000))
    while True:
        payload = _get("/account/api/internal/students", {"page": page, "page_size": page_size})
        students = payload.get("students")
        if not isinstance(students, list):
            raise PlatformAccountError("平台账号服务返回结构不正确")
        if not students:
            return
        for student in students:
            if isinstance(student, dict):
                yield student
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
        if len(students) < page_size:
            return
        page += 1
