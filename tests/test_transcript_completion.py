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
sys.modules.setdefault("aliyunsdkcore", SimpleNamespace())
sys.modules.setdefault("aliyunsdkcore.client", SimpleNamespace(AcsClient=object))
sys.modules.setdefault("aliyunsdkcore.request", SimpleNamespace(CommonRequest=object))

from core import llm_agent


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        return SimpleNamespace(content=self.responses[len(self.calls) - 1])


def test_final_answer_is_included_in_chat_history(monkeypatch):
    fake_llm = FakeLLM(
        [
            '{"spoken":"first","display":"first"}',
            '{"spoken":"q2","display":"q2"}',
            '{"spoken":"q3","display":"q3"}',
            '{"spoken":"q4","display":"q4"}',
            '{"spoken":"q5","display":"q5"}',
            '{"spoken":"q6","display":"q6"}',
        ]
    )
    monkeypatch.setattr(llm_agent, "llm", fake_llm)
    monkeypatch.setattr(llm_agent, "_build_question_sequence", lambda lang: ["q1", "q2", "q3", "q4", "q5", "q6"])
    monkeypatch.setattr(llm_agent.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(
        llm_agent,
        "load_runtime_prompts",
        lambda: (llm_agent.DEFAULT_BASE_PROMPT, llm_agent.DEFAULT_EVAL_PROMPT),
    )

    session_id, _ = llm_agent.create_interview_session("en")
    for index in range(5):
        llm_agent.generate_interview_response(session_id, f"answer {index + 1}")

    result = llm_agent.generate_interview_response(session_id, "final answer")
    transcript = llm_agent.get_chat_history_string(session_id)

    assert result["is_end"] is True
    assert "final answer" in transcript
    assert "Thank you very much" in transcript
