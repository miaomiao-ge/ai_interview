import json
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

INSTRUMENT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assessments", "bsi53.v1.json"
)

DIMENSIONS = {
    "SOM": [2, 7, 23, 29, 30, 33, 37],
    "OC": [5, 15, 26, 27, 32, 36],
    "IS": [20, 21, 22, 42],
    "DEP": [9, 16, 17, 18, 35, 50],
    "ANX": [1, 12, 19, 38, 45, 49],
    "HOS": [6, 13, 40, 41, 46],
    "PHOB": [8, 28, 31, 43, 47],
    "PAR": [4, 10, 24, 48, 51],
    "PSY": [3, 14, 34, 44, 53],
}

TOTAL_ITEMS = 53


def _round3(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def load_instrument() -> dict:
    with open(INSTRUMENT_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _normalize(answers: dict) -> dict:
    normalized = {}
    for key, value in (answers or {}).items():
        normalized[int(key)] = int(value)
    return normalized


def validate_answers(answers: dict) -> Optional[str]:
    if not answers:
        return "Answers are required"
    normalized = _normalize(answers)
    if len(normalized) != TOTAL_ITEMS:
        return "All 53 items must be answered"
    for no in range(1, TOTAL_ITEMS + 1):
        value = normalized.get(no)
        if value is None:
            return "All 53 items must be answered"
        if value < 0 or value > 4:
            return "Each answer must be within 0-4"
    return None


def score_answers(answers: dict) -> dict:
    normalized = _normalize(answers)
    error = validate_answers(normalized)
    if error:
        raise ValueError(error)

    dimensions = {}
    for code, items in DIMENSIONS.items():
        total = sum(normalized[no] for no in items)
        dimensions[code] = _round3(total / len(items))

    total = sum(normalized[no] for no in range(1, TOTAL_ITEMS + 1))
    pst = sum(1 for no in range(1, TOTAL_ITEMS + 1) if normalized[no] > 0)
    gsi = _round3(total / TOTAL_ITEMS)
    psdi = 0.0 if pst == 0 else _round3(total / pst)

    risk_items = []
    if normalized[9] > 0:
        risk_items.append({"no": 9, "value": normalized[9]})
    if normalized[39] > 0:
        risk_items.append({"no": 39, "value": normalized[39]})
    for no in (40, 41):
        if normalized[no] >= 3:
            risk_items.append({"no": no, "value": normalized[no]})

    risk_level = "NONE"
    if risk_items:
        risk_level = "WATCH"
    if normalized[9] >= 2 or normalized[39] >= 2:
        risk_level = "URGENT"

    return {
        "dimensions": dimensions,
        "gsi": gsi,
        "pst": pst,
        "psdi": psdi,
        "risk_level": risk_level,
        "risk_items": risk_items,
    }
