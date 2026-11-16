from routers.user_api import asr_empty_response, choose_better_asr_text


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


def test_choose_better_asr_text_keeps_server_result_when_comparable():
    text, source = choose_better_asr_text("我来自哈萨克斯坦，喜欢打篮球和看书。", "我来自哈萨克斯坦，喜欢打篮球。", "realtime_ws_asr")

    assert text == "我来自哈萨克斯坦，喜欢打篮球和看书。"
    assert source == "realtime_ws_asr"


def test_choose_better_asr_text_prefers_browser_transcript_when_server_result_is_short():
    text, source = choose_better_asr_text("暴雪SE。遗产。", "我本科毕业于阿拉木图国立大学，专业是计算机科学。", "realtime_ws_asr")

    assert text == "我本科毕业于阿拉木图国立大学，专业是计算机科学。"
    assert source == "fallback_text"


def test_choose_better_asr_text_uses_browser_transcript_when_server_result_empty():
    text, source = choose_better_asr_text("", "我在本科学习中遇到问题会先查资料。", "realtime_ws_asr")

    assert text == "我在本科学习中遇到问题会先查资料。"
    assert source == "fallback_text"


def test_choose_better_asr_text_returns_empty_when_both_missing():
    text, source = choose_better_asr_text("  ", "", "realtime_ws_asr")

    assert text == ""
    assert source == "realtime_ws_asr"
