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

from core import llm_agent


def test_evaluation_guardrails_mark_short_english_as_possible_asr_loss():
    state = SimpleNamespace(language="en")
    prompt = llm_agent._build_evaluation_guardrails(state, ["computer science", "xidian"])

    assert "possible_asr_loss" in prompt
    assert "ASR" in prompt
    assert "language" in prompt.lower()


def test_calibration_protects_english_language_score_for_possible_asr_loss():
    state = SimpleNamespace(language="en")
    payload = {
        "total_score": 25,
        "dimension_scores": [
            {"name": "intro", "score": 5, "comment": ""},
            {"name": "major", "score": 5, "comment": ""},
            {"name": "motivation", "score": 5, "comment": ""},
            {"name": "adaptability", "score": 5, "comment": ""},
            {"name": "language", "score": 4, "comment": "weak"},
        ],
    }

    result = llm_agent._calibrate_evaluation_payload(payload, state, ["computer science", "xidian"])

    assert result["dimension_scores"][-1]["score"] == 8
    assert result["total_score"] == 28
    assert "ASR" in result["dimension_scores"][-1]["comment"]
