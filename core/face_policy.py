import json
from collections import Counter

from core.config import FACE_COMPARE_THRESHOLD

RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

HIGH_RISK_FLAGS = {"multiple_faces", "multiple_persons"}
MEDIUM_RISK_FLAGS = {"no_face", "person_absent", "head_down", "head_turned", "face_not_centered"}
CRITICAL_RISK_FLAGS = {"identity_recheck_failed"}


def compare_passed(score: float | int | None) -> bool:
    try:
        return float(score) >= FACE_COMPARE_THRESHOLD
    except (TypeError, ValueError):
        return False


def risk_for_flags(flags: list[str]) -> str:
    flag_set = set(flags or [])
    if flag_set & CRITICAL_RISK_FLAGS:
        return "critical"
    if flag_set & HIGH_RISK_FLAGS:
        return "high"
    if flag_set & MEDIUM_RISK_FLAGS:
        return "medium"
    return "none"


def max_risk(left: str, right: str) -> str:
    return left if RISK_ORDER.get(left or "none", 0) >= RISK_ORDER.get(right or "none", 0) else right


def aggregate_proctoring_flags(existing_json: str | None, new_flags: list[str]) -> str:
    counts = Counter()
    if existing_json:
        try:
            data = json.loads(existing_json)
            if isinstance(data, dict):
                counts.update({str(k): int(v or 0) for k, v in data.items()})
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    counts.update(new_flags or [])
    return json.dumps(dict(counts), ensure_ascii=False)
