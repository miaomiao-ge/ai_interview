import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

from core.config import ALI_AK_ID, ALI_AK_SECRET, ALI_FACEBODY_ENDPOINT
from core.face_policy import risk_for_flags


def _request(action: str, params: dict[str, Any]) -> dict:
    if not ALI_AK_ID or not ALI_AK_SECRET:
        raise RuntimeError("Aliyun access key is not configured")

    client = AcsClient(ALI_AK_ID, ALI_AK_SECRET, "cn-shanghai")
    request = CommonRequest()
    request.set_method("POST")
    request.set_domain(ALI_FACEBODY_ENDPOINT)
    request.set_version("2019-12-30")
    request.set_action_name(action)
    for key, value in params.items():
        if value is not None and value != "":
            request.add_query_param(key, value)
    response = client.do_action_with_exception(request)
    return json.loads(response)


def _provider_image_url(image_url: str) -> str:
    """Facebody fetches the image itself; keep the signed URL on public HTTPS."""
    parts = urlsplit(image_url)
    host = parts.netloc
    if host.endswith("-internal.aliyuncs.com"):
        host = host.replace("-internal.aliyuncs.com", ".aliyuncs.com")
    return urlunsplit(("https", host, parts.path, parts.query, ""))


def _first_score(data: Any) -> float | None:
    if isinstance(data, dict):
        for key in ("Score", "Confidence", "Rate"):
            if key in data:
                try:
                    return float(data[key])
                except (TypeError, ValueError):
                    pass
        for value in data.values():
            score = _first_score(value)
            if score is not None:
                return score
    if isinstance(data, list):
        for item in data:
            score = _first_score(item)
            if score is not None:
                return score
    return None


def _contains_success(data: Any) -> bool:
    text = json.dumps(data, ensure_ascii=False).lower()
    return any(item in text for item in ("normal", "success", "live", "true", "pass"))


def detect_living_face(image_url: str) -> dict:
    image_url = _provider_image_url(image_url)
    raw = _request("DetectLivingFace", {"Tasks.1.ImageURL": image_url})
    data = raw.get("Data") or raw
    passed = _contains_success(data)
    return {
        "ok": True,
        "provider": "aliyun_facebody",
        "action": "DetectLivingFace",
        "request_id": raw.get("RequestId", ""),
        "passed": passed,
        "score": _first_score(data),
        "flags": [] if passed else ["liveness_failed"],
        "raw": raw,
    }


def compare_face(source_url: str, target_url: str) -> dict:
    source_url = _provider_image_url(source_url)
    target_url = _provider_image_url(target_url)
    raw = _request("CompareFace", {"ImageURLA": source_url, "ImageURLB": target_url})
    data = raw.get("Data") or raw
    score = _first_score(data)
    return {
        "ok": True,
        "provider": "aliyun_facebody",
        "action": "CompareFace",
        "request_id": raw.get("RequestId", ""),
        "passed": False,
        "score": score,
        "flags": [],
        "raw": raw,
    }


def _monitor_flags(raw: dict) -> list[str]:
    text = json.dumps(raw, ensure_ascii=False).lower()
    flag_map = {
        "no_face": ("noface", "no face", "无人脸", "未检测到人脸"),
        "multiple_faces": ("multipleface", "multiple face", "多脸", "多个人脸"),
        "multiple_persons": ("multipleperson", "multiple person", "多人"),
        "head_down": ("headdown", "head down", "低头"),
        "head_turned": ("headturn", "turned", "侧脸", "转头"),
        "phone_detected": ("phone", "mobile", "手机"),
        "earphone_detected": ("earphone", "headphone", "耳机"),
    }
    ignored_flags = {"phone_detected", "earphone_detected"}
    return [
        flag
        for flag, needles in flag_map.items()
        if flag not in ignored_flags and any(needle in text for needle in needles)
    ]


def monitor_examination(image_url: str) -> dict:
    image_url = _provider_image_url(image_url)
    raw = _request("MonitorExamination", {"ImageURL": image_url, "Type": 1})
    flags = _monitor_flags(raw)
    return {
        "ok": True,
        "provider": "aliyun_facebody",
        "action": "MonitorExamination",
        "request_id": raw.get("RequestId", ""),
        "passed": not flags,
        "score": None,
        "flags": flags,
        "risk_level": risk_for_flags(flags),
        "raw": raw,
    }
