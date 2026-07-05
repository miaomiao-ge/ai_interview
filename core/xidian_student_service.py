import base64
import re
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from core.config import (
    XIDIAN_STUDENT_API_BASE_URL,
    XIDIAN_STUDENT_APP_KEY,
    XIDIAN_STUDENT_APP_SECRET,
    XIDIAN_STUDENT_PHOTO_MAX_BYTES,
    XIDIAN_STUDENT_REQUEST_TIMEOUT_SECONDS,
)


APPLICATION_NO_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


class XidianStudentApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class OfficialPhoto:
    content: bytes
    extension: str


def _require_credentials() -> None:
    if not XIDIAN_STUDENT_APP_KEY or not XIDIAN_STUDENT_APP_SECRET:
        raise XidianStudentApiError(
            "未配置 XIDIAN_STUDENT_APP_KEY / XIDIAN_STUDENT_APP_SECRET"
        )


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        raise XidianStudentApiError("学生信息接口 HTTP 请求失败") from None
    try:
        payload = response.json()
    except ValueError as exc:
        raise XidianStudentApiError("学生信息接口返回了无效 JSON") from exc
    if not isinstance(payload, dict):
        raise XidianStudentApiError("学生信息接口返回结构不正确")
    return payload


def get_access_token(client: httpx.Client) -> str:
    _require_credentials()
    try:
        response = client.get(
            f"{XIDIAN_STUDENT_API_BASE_URL}/getToken",
            params={
                "appKey": XIDIAN_STUDENT_APP_KEY,
                "appSecret": XIDIAN_STUDENT_APP_SECRET,
            },
        )
    except httpx.HTTPError:
        raise XidianStudentApiError("学生信息接口连接失败") from None
    payload = _response_json(response)
    token = payload.get("dataObject")
    if str(payload.get("result")) != "1" or not payload.get("valid") or not isinstance(token, str) or not token:
        raise XidianStudentApiError(str(payload.get("message") or "获取访问令牌失败"))
    return token


def get_application_page(
    client: httpx.Client,
    token: str,
    year: int,
    page_num: int,
    page_size: int = 100,
    application_nos: list[str] | None = None,
) -> dict[str, Any]:
    if year < 2026:
        raise ValueError("year 不能早于 2026")
    if page_num < 1:
        raise ValueError("page_num 必须大于 0")
    if not 1 <= page_size <= 100:
        raise ValueError("page_size 必须在 1 到 100 之间")

    form = {
        "token": token,
        "year": str(year),
        "pageNum": str(page_num),
        "pageSize": str(page_size),
    }
    if application_nos:
        cleaned = [str(value).strip() for value in application_nos]
        if any(not APPLICATION_NO_PATTERN.fullmatch(value) for value in cleaned):
            raise ValueError("application_nos 中存在格式错误的申请编号")
        form["applicationNos"] = ",".join(cleaned)

    try:
        response = client.post(
            f"{XIDIAN_STUDENT_API_BASE_URL}/getApplicationInfoBatch",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    except httpx.HTTPError:
        raise XidianStudentApiError("学生信息接口连接失败") from None
    payload = _response_json(response)
    if str(payload.get("result")) != "1" or not payload.get("valid"):
        raise XidianStudentApiError(str(payload.get("message") or "获取申请数据失败"))
    data_object = payload.get("dataObject")
    if not isinstance(data_object, dict) or not isinstance(data_object.get("data"), list):
        raise XidianStudentApiError("申请数据返回结构不正确")
    return data_object


def iter_applications(
    year: int,
    application_nos: list[str] | None = None,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    if limit is not None and limit < 1:
        raise ValueError("limit 必须大于 0")
    timeout = httpx.Timeout(XIDIAN_STUDENT_REQUEST_TIMEOUT_SECONDS)
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        token = get_access_token(client)
        page_num = 1
        yielded = 0
        page_size = min(100, limit) if limit is not None else 100
        while True:
            page = get_application_page(client, token, year, page_num, page_size, application_nos)
            records = page["data"]
            for record in records:
                if isinstance(record, dict):
                    yield record
                    yielded += 1
                    if limit is not None and yielded >= limit:
                        return

            total_count = int(page.get("totalCount") or 0)
            if page_num * page_size >= total_count or not records:
                break
            page_num += 1


def decode_official_photo(value: str) -> OfficialPhoto:
    encoded = (value or "").strip()
    if encoded.startswith("data:"):
        _, separator, encoded = encoded.partition(",")
        if not separator:
            raise XidianStudentApiError("照片 Data URL 格式错误")
    try:
        content = base64.b64decode("".join(encoded.split()), validate=True)
    except (TypeError, ValueError) as exc:
        raise XidianStudentApiError("照片不是有效的 Base64 数据") from exc
    if not content or len(content) > XIDIAN_STUDENT_PHOTO_MAX_BYTES:
        raise XidianStudentApiError("照片为空或超过大小限制")
    if content.startswith(b"\xff\xd8\xff"):
        return OfficialPhoto(content, "jpg")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return OfficialPhoto(content, "png")
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return OfficialPhoto(content, "webp")
    raise XidianStudentApiError("照片格式仅支持 JPEG、PNG 或 WebP")
