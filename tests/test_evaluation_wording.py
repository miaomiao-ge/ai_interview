from core.llm_agent import soften_evaluation_payload, soften_evaluation_wording


def test_softens_blunt_negative_words():
    text = "该考生表达较差，专业认知不足，缺乏规划，回答问题不合格。"

    softened = soften_evaluation_wording(text)

    for banned in ("较差", "不足", "缺乏", "不合格"):
        assert banned not in softened
    assert "可进一步" in softened or "建议" in softened


def test_keeps_neutral_text_unchanged():
    text = "表达自然，专业方向清晰，具备基本适应能力。"

    assert soften_evaluation_wording(text) == text


def test_payload_softening_covers_nested_fields():
    payload = {
        "total_score": 60,
        "summary": "整体表现不足，语言能力偏弱。",
        "strengths": ["态度认真"],
        "improvements": ["专业认知缺乏深度"],
        "dimension_scores": [
            {"name": "语言能力", "score": 10, "comment": "表达较差"},
        ],
    }

    softened = soften_evaluation_payload(payload)

    assert "不足" not in softened["summary"]
    assert "偏弱" not in softened["summary"]
    assert "缺乏" not in softened["improvements"][0]
    assert "较差" not in softened["dimension_scores"][0]["comment"]
    assert softened["total_score"] == 60
