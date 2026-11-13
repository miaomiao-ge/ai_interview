"""Client for the platform account service's internal student endpoint.

Only account metadata and password hashes cross this boundary; plaintext
passwords never leave the AI interview service.
"""
import httpx

from core.config import (
    PLATFORM_ACCOUNT_PAGE_SIZE,
    PLATFORM_ACCOUNT_SOURCES,
    PLATFORM_ACCOUNT_SYNC_TIMEOUT_SECONDS,
)


class PlatformAccountError(RuntimeError):
    pass


def _source_label(source: dict) -> str:
    return str(source.get("name") or "platform").strip() or "platform"


def _headers(source: dict) -> dict:
    token = str(source.get("token") or "").strip()
    if not token:
        raise PlatformAccountError("未配置平台账号同步凭证")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _get(path: str, params: dict, source: dict) -> dict:
    base = str(source.get("base") or "").rstrip("/")
    if not base:
        raise PlatformAccountError("未配置平台账号服务地址")
    url = f"{base}{path}"
    timeout = httpx.Timeout(PLATFORM_ACCOUNT_SYNC_TIMEOUT_SECONDS)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.get(url, params=params, headers=_headers(source))
    except httpx.HTTPError as exc:
        raise PlatformAccountError(f"平台账号服务({_source_label(source)})连接失败") from exc
    if response.status_code == 401:
        raise PlatformAccountError(f"平台账号服务({_source_label(source)})拒绝了同步凭证")
    if response.status_code != 200:
        raise PlatformAccountError(f"平台账号服务({_source_label(source)})返回异常状态")
    try:
        payload = response.json()
    except ValueError as exc:
        raise PlatformAccountError(f"平台账号服务({_source_label(source)})返回了无效 JSON") from exc
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise PlatformAccountError(f"平台账号服务({_source_label(source)})返回结构不正确")
    return payload


def fetch_students(account: str, source_name: str | None = None) -> list[tuple[dict, dict]]:
    """Return every (source, student) match across configured environment sources."""
    candidates: list[tuple[dict, dict]] = []
    errors: list[PlatformAccountError] = []
    wanted = (source_name or "").strip().lower()
    sources = [s for s in PLATFORM_ACCOUNT_SOURCES if not wanted or _source_label(s).lower() == wanted]
    for source in sources:
        try:
            payload = _get(
                "/account/api/internal/students",
                {"account": account, "page": 1, "page_size": 1},
                source,
            )
        except PlatformAccountError as exc:
            errors.append(exc)
            continue
        students = payload.get("students")
        if not isinstance(students, list):
            errors.append(PlatformAccountError(f"平台账号服务({_source_label(source)})返回结构不正确"))
            continue
        for student in students:
            if isinstance(student, dict):
                candidates.append((source, student))
    if errors and len(errors) == len(sources):
        raise PlatformAccountError("平台账号服务暂时不可用")
    return candidates


def fetch_student(account: str, source_name: str | None = None) -> tuple[dict, dict] | tuple[None, None]:
    candidates = fetch_students(account, source_name)
    if not candidates:
        return None, None
    return candidates[0]


def fetch_student_photo(account: str, source: dict | None = None) -> dict | None:
    """Return {"kind":"oss",...} or {"kind":"bytes","content":...,"extension":...}."""
    sources = [source] if source else list(PLATFORM_ACCOUNT_SOURCES)
    errors: list[PlatformAccountError] = []
    for candidate in sources:
        try:
            photo = _fetch_photo_from_source(account, candidate)
        except PlatformAccountError as exc:
            errors.append(exc)
            continue
        if photo is not None:
            return photo
    if errors and len(errors) == len(sources):
        raise PlatformAccountError("平台照片服务暂时不可用")
    return None


def _fetch_photo_from_source(account: str, source: dict) -> dict | None:
    base = str(source.get("base") or "").rstrip("/")
    if not base:
        raise PlatformAccountError("未配置平台账号服务地址")
    url = f"{base}/account/api/internal/students/photo"
    timeout = httpx.Timeout(PLATFORM_ACCOUNT_SYNC_TIMEOUT_SECONDS)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.get(url, params={"account": account}, headers=_headers(source))
    except httpx.HTTPError as exc:
        raise PlatformAccountError(f"平台照片服务({_source_label(source)})连接失败") from exc
    if response.status_code == 404:
        return None
    if response.status_code == 401:
        raise PlatformAccountError(f"平台账号服务({_source_label(source)})拒绝了同步凭证")
    if response.status_code != 200:
        raise PlatformAccountError(f"平台照片服务({_source_label(source)})返回异常状态")
    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = response.json()
        except ValueError as exc:
            raise PlatformAccountError(f"平台照片服务({_source_label(source)})返回了无效 JSON") from exc
        if not isinstance(payload, dict) or payload.get("kind") != "oss" or not payload.get("key"):
            raise PlatformAccountError(f"平台照片服务({_source_label(source)})返回结构不正确")
        return payload
    if content_type.startswith("image/"):
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
        return {"kind": "bytes", "content": response.content, "extension": extension}
    raise PlatformAccountError(f"平台照片服务({_source_label(source)})返回了不支持的类型")


def iter_students(limit: int | None = None, source: dict | None = None):
    sources = [source] if source else list(PLATFORM_ACCOUNT_SOURCES)
    yielded = 0
    page_size = max(1, min(PLATFORM_ACCOUNT_PAGE_SIZE, 1000))
    for candidate in sources:
        page = 1
        while True:
            payload = _get(
                "/account/api/internal/students",
                {"page": page, "page_size": page_size},
                candidate,
            )
            students = payload.get("students")
            if not isinstance(students, list):
                raise PlatformAccountError(
                    f"平台账号服务({_source_label(candidate)})返回结构不正确"
                )
            if not students:
                break
            for student in students:
                if isinstance(student, dict):
                    yield candidate, student
                    yielded += 1
                    if limit is not None and yielded >= limit:
                        return
            if len(students) < page_size:
                break
            page += 1
