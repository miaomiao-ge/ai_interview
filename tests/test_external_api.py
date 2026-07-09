import json
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import external_api


def run_async(coro):
    return asyncio.run(coro)


def test_verify_external_api_key_accepts_bearer(monkeypatch):
    monkeypatch.setattr(external_api, "EXTERNAL_RESULT_API_KEY", "secret")

    external_api.verify_external_api_key(authorization="Bearer secret")


def test_verify_external_api_key_rejects_missing_configuration(monkeypatch):
    monkeypatch.setattr(external_api, "EXTERNAL_RESULT_API_KEY", "")

    with pytest.raises(HTTPException) as exc:
        external_api.verify_external_api_key(authorization="Bearer secret")

    assert exc.value.status_code == 503


def test_get_token_returns_pdf_style_payload(monkeypatch):
    monkeypatch.setattr(external_api, "EXTERNAL_RESULT_APP_KEY", "app-key")
    monkeypatch.setattr(external_api, "EXTERNAL_RESULT_APP_SECRET", "app-secret")

    payload = run_async(external_api.get_external_result_token(appKey="app-key", appSecret="app-secret"))

    assert payload["result"] == "1"
    assert payload["valid"] is True
    assert payload["dataObject"]
    ok, message = external_api.verify_external_token(payload["dataObject"])
    assert ok is True
    assert message == ""


def test_get_batch_requires_valid_token():
    payload = run_async(
        external_api.get_application_interview_result_batch(
            token="bad-token",
            year="2026",
            pageNum=1,
            pageSize=100,
        )
    )

    assert payload["result"] == "0"
    assert payload["valid"] is False


def test_serialize_result_row_includes_student_and_interview_result():
    user = SimpleNamespace(
        real_name="DU TEST",
        family_name="TEST",
        given_name="DU",
        xidian_application_id="APP-1",
        xidian_application_no="20260600003",
        xidian_recommend_flag="1",
        passport_no="AQ1234567",
        email="student@example.com",
    )
    record = SimpleNamespace(
        id=12,
        session_id="session-1",
        evaluate_status="success",
        archive_status="success",
        archive_error="",
        review_status="待复核",
        review_remark="",
        evaluation_result="综合得分：88/100",
        evaluation_result_json=json.dumps(
            {
                "total_score": 88,
                "dimension_scores": [{"name": "语言能力", "score": 18, "comment": "表达清楚"}],
                "summary": "整体表现良好",
                "strengths": ["表达清楚"],
                "improvements": ["补充研究计划"],
            },
            ensure_ascii=False,
        ),
        chat_history="Q: ...\nA: ...",
        face_verify_status="passed",
        face_verify_score=91.2,
        face_verify_at=datetime(2026, 7, 9, 10, 0, 0),
        face_verify_snapshot_oss_key="face/snapshot.jpg",
        identity_doc_oss_key="face/doc.jpg",
        proctoring_risk_level="low",
        proctoring_flags_json=json.dumps({"no_person": 0}),
        audio_path="",
        video_path="",
        av_path="https://oss.example/interview.mp4",
        submitted_at=datetime(2026, 7, 9, 10, 1, 0),
        completed_at=datetime(2026, 7, 9, 10, 20, 0),
        processing_started_at=datetime(2026, 7, 9, 10, 19, 0),
        processing_finished_at=datetime(2026, 7, 9, 10, 20, 0),
        created_at=datetime(2026, 7, 9, 10, 0, 0),
    )

    payload = external_api.serialize_result_row(user, record)

    assert payload["name"] == "DU TEST"
    assert payload["familyName"] == "TEST"
    assert payload["givenName"] == "DU"
    assert payload["id"] == "APP-1"
    assert payload["applicationNo"] == "20260600003"
    assert payload["flag"] == "1"
    assert payload["interviewResult"]["totalScore"] == 88
    assert payload["interviewResult"]["dimensionScores"][0]["score"] == 18
    assert payload["interviewResult"]["faceVerification"]["status"] == "passed"
    assert payload["interviewResult"]["media"]["avPath"].endswith("interview.mp4")
