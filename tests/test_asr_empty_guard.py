from routers.user_api import asr_empty_response


def test_asr_empty_response_uses_retryable_error_code():
    response = asr_empty_response("zh")

    assert response["status"] == "error"
    assert response["code"] == "asr_empty"
    assert "重新回答" in response["message"]


def test_asr_empty_response_supports_english_language_variants():
    response = asr_empty_response("en-US")

    assert response["status"] == "error"
    assert response["code"] == "asr_empty"
    assert "answer again" in response["message"]
