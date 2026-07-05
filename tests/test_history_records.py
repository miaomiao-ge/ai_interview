import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_message_type = lambda name: type(name, (), {"__init__": lambda self, content: setattr(self, "content", content)})
sys.modules.setdefault(
    "langchain_openai",
    SimpleNamespace(ChatOpenAI=lambda *args, **kwargs: SimpleNamespace(invoke=lambda messages: None)),
)
sys.modules.setdefault(
    "langchain_core.messages",
    SimpleNamespace(
        HumanMessage=_message_type("HumanMessage"),
        SystemMessage=_message_type("SystemMessage"),
        AIMessage=_message_type("AIMessage"),
    ),
)
sys.modules.setdefault(
    "pymysql",
    SimpleNamespace(
        paramstyle="pyformat",
        threadsafety=1,
        apilevel="2.0",
        connect=lambda *args, **kwargs: None,
    ),
)
sys.modules.setdefault("aliyunsdkcore.client", SimpleNamespace(AcsClient=object))
sys.modules.setdefault("aliyunsdkcore.request", SimpleNamespace(CommonRequest=object))

from core import database
from core import llm_agent


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        return SimpleNamespace(content=self.responses[len(self.calls) - 1])


def _fixed_questions():
    return {
        "个人基本情况与留学动机": ["问题一"],
        "学术背景与学习能力": ["问题二"],
        "专业认知与申请规划": ["问题三"],
        "跨文化交流能力": ["问题四"],
        "综合素质": ["问题五"],
    }


def test_interview_record_user_email_is_not_unique():
    user_email_column = database.InterviewRecord.__table__.c.user_email

    assert not user_email_column.unique


def test_interview_record_model_exposes_structured_report_column():
    assert hasattr(database.InterviewRecord, "evaluation_result_json")


def test_render_evaluation_report_from_structured_payload():
    payload = {
        "candidate_name": "Alice",
        "language": "zh",
        "total_score": 86,
        "dimension_scores": [
            {"name": "自我介绍与表达", "score": 18, "comment": "表达自然，重点清晰"},
            {"name": "专业匹配度", "score": 17, "comment": "专业基础较扎实"},
            {"name": "学习动机与规划", "score": 17, "comment": "规划相对清楚"},
            {"name": "综合素养与适应能力", "score": 17, "comment": "沟通积极，有配合度"},
            {"name": "语言能力", "score": 17, "comment": "交流顺畅"},
        ],
        "strengths": ["表达流畅", "学习目标明确"],
        "improvements": ["补充更具体的研究兴趣"],
        "summary": "整体表现稳定，具备较好的复试潜力。",
    }

    report = llm_agent.render_structured_evaluation_report(payload)

    assert "综合得分：86/100" in report
    assert "自我介绍与表达" in report
    assert "核心优势" in report


def test_parse_structured_evaluation_json_strips_code_fences():
    raw = """```json
    {"candidate_name":"Alice","language":"zh","total_score":80,"dimension_scores":[],"strengths":[],"improvements":[],"summary":"ok"}
    ```"""

    parsed = llm_agent.parse_structured_evaluation(raw)

    assert parsed["total_score"] == 80


def test_parse_structured_evaluation_extracts_json_from_extra_text():
    raw = """
    Here is the report:
    {"candidate_name":"Alice","language":"zh","total_score":70,"dimension_scores":[],"strengths":[],"improvements":[],"summary":"ok"}
    Done.
    """

    parsed = llm_agent.parse_structured_evaluation(raw)

    assert parsed["total_score"] == 70


def test_parse_structured_evaluation_accepts_chinese_key_report():
    raw = json.dumps(
        {
            "\u7efc\u5408\u5f97\u5206": 25,
            "\u5404\u9879\u5f97\u5206\u4e0e\u8bc4\u4ef7": {
                "\u81ea\u6211\u4ecb\u7ecd\u4e0e\u8868\u8fbe": {
                    "\u5f97\u5206": 5,
                    "\u7b80\u8bc4": "\u5019\u9009\u4eba\u672a\u5b8c\u6210\u57fa\u672c\u81ea\u6211\u4ecb\u7ecd\u3002",
                },
                "\u4e13\u4e1a\u5339\u914d\u5ea6": {
                    "\u5f97\u5206": 5,
                    "\u7b80\u8bc4": "\u4e13\u4e1a\u57fa\u7840\u8584\u5f31\u3002",
                },
            },
            "\u6838\u5fc3\u4f18\u52bf": [],
            "\u6539\u8fdb\u5efa\u8bae": ["\u9700\u5168\u9762\u63d0\u5347\u8bed\u8a00\u6c9f\u901a\u80fd\u529b\u3002"],
        },
        ensure_ascii=False,
    )

    parsed = llm_agent.parse_structured_evaluation(raw)

    assert parsed["total_score"] == 25
    assert parsed["language"] == "zh"
    assert parsed["dimension_scores"][0]["score"] == 5
    assert parsed["improvements"] == ["\u9700\u5168\u9762\u63d0\u5347\u8bed\u8a00\u6c9f\u901a\u80fd\u529b\u3002"]


def test_evaluation_handles_all_no_answer_without_llm_eval_call(monkeypatch):
    fake_llm = FakeLLM(
        [
            '{"spoken":"first","display":"first"}',
            '{"spoken":"next","display":"next"}',
        ]
    )
    monkeypatch.setattr(llm_agent, "llm", fake_llm)
    monkeypatch.setattr(llm_agent, "load_questions", _fixed_questions)
    monkeypatch.setattr(llm_agent.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(
        llm_agent,
        "load_runtime_prompts",
        lambda: (llm_agent.DEFAULT_BASE_PROMPT, llm_agent.DEFAULT_EVAL_PROMPT),
    )

    session_id, _ = llm_agent.create_interview_session("zh")
    llm_agent.generate_interview_response(
        session_id,
        "\u3010\u5019\u9009\u4eba\u672a\u4f5c\u7b54 / No Answer\u3011",
    )

    result = llm_agent.evaluate_interview(session_id)

    assert result["structured"]["total_score"] == 0
    assert len(fake_llm.calls) == 2


def test_build_evaluation_result_contains_report_and_json(monkeypatch):
    fake_llm = FakeLLM(
        [
            '{"spoken":"开场","display":"开场"}',
            '{"spoken":"追问","display":"追问"}',
            json.dumps(
                {
                    "candidate_name": "Alice",
                    "language": "zh",
                    "total_score": 80,
                    "dimension_scores": [
                        {"name": "自我介绍与表达", "score": 16, "comment": "表达较完整"},
                        {"name": "专业匹配度", "score": 16, "comment": "基础较扎实"},
                    ],
                    "strengths": ["表达完整"],
                    "improvements": ["补充更多案例"],
                    "summary": "整体表现较稳定",
                },
                ensure_ascii=False,
            ),
        ]
    )
    monkeypatch.setattr(llm_agent, "llm", fake_llm)
    monkeypatch.setattr(llm_agent, "load_questions", _fixed_questions)
    monkeypatch.setattr(llm_agent.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(
        llm_agent,
        "load_runtime_prompts",
        lambda: (llm_agent.DEFAULT_BASE_PROMPT, llm_agent.DEFAULT_EVAL_PROMPT),
    )

    session_id, _ = llm_agent.create_interview_session("zh")
    llm_agent.generate_interview_response(session_id, "我的回答")

    result = llm_agent.evaluate_interview(session_id)

    assert result["structured"]["total_score"] == 80
    assert "综合得分：80/100" in result["report"]
