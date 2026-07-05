import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault(
    "langchain_openai",
    SimpleNamespace(ChatOpenAI=lambda *args, **kwargs: SimpleNamespace(invoke=lambda messages: None)),
)
sys.modules.setdefault("aliyunsdkcore.client", SimpleNamespace(AcsClient=object))
sys.modules.setdefault("aliyunsdkcore.request", SimpleNamespace(CommonRequest=object))
_message_type = lambda name: type(name, (), {"__init__": lambda self, content: setattr(self, "content", content)})
sys.modules.setdefault(
    "langchain_core.messages",
    SimpleNamespace(
        HumanMessage=_message_type("HumanMessage"),
        SystemMessage=_message_type("SystemMessage"),
        AIMessage=_message_type("AIMessage"),
    ),
)
sys.modules.setdefault(
    "core.database",
    SimpleNamespace(
        SessionLocal=lambda: None,
        QuestionBank=SimpleNamespace(),
        PromptConfig=SimpleNamespace(),
    ),
)

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


def test_sessions_keep_independent_question_progress(monkeypatch):
    fake_llm = FakeLLM(
        [
            '{"spoken":"开场A","display":"开场A"}',
            '{"spoken":"开场B","display":"开场B"}',
            '{"spoken":"继续A1","display":"继续A1"}',
            '{"spoken":"继续A2","display":"继续A2"}',
            '{"spoken":"继续B1","display":"继续B1"}',
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

    session_a, _ = llm_agent.create_interview_session("zh")
    session_b, _ = llm_agent.create_interview_session("zh")

    llm_agent.generate_interview_response(session_a, "A-回答-1")
    llm_agent.generate_interview_response(session_a, "A-回答-2")
    llm_agent.generate_interview_response(session_b, "B-回答-1")

    session_a_last_prompt = fake_llm.calls[3][-1].content
    session_b_last_prompt = fake_llm.calls[4][-1].content

    assert "问题二" in session_a_last_prompt
    assert "问题一" in session_b_last_prompt


def test_runtime_prompts_override_defaults(monkeypatch):
    fake_llm = FakeLLM(
        [
            '{"spoken":"开场","display":"开场"}',
            '{"spoken":"追问","display":"追问"}',
            "评估报告",
        ]
    )
    monkeypatch.setattr(llm_agent, "llm", fake_llm)
    monkeypatch.setattr(llm_agent, "load_questions", _fixed_questions)
    monkeypatch.setattr(llm_agent.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(
        llm_agent,
        "load_runtime_prompts",
        lambda: ("自定义基础Prompt", "自定义评估Prompt\n{transcript}"),
    )

    session_id, _ = llm_agent.create_interview_session("zh")
    llm_agent.generate_interview_response(session_id, "候选人回答")
    llm_agent.evaluate_interview(session_id)

    init_system_prompt = fake_llm.calls[0][0].content
    eval_system_prompt = fake_llm.calls[2][0].content

    assert init_system_prompt.startswith("自定义基础Prompt")
    assert "自定义评估Prompt" in eval_system_prompt
    assert "候选人: 候选人回答" in eval_system_prompt


def test_first_question_is_sanitized_to_selected_chinese(monkeypatch):
    fake_llm = FakeLLM(
        [
            '{"spoken":"你好！欢迎参加西电的面试。\\n\\nHello! Welcome to the interview.\\n\\nПривет! Добро пожаловать на собеседование.","display":"你好！欢迎参加西电的面试。\\n\\nHello! Welcome to the interview.\\n\\nПривет! Добро пожаловать на собеседование."}'
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

    _, first_question = llm_agent.create_interview_session("zh")

    parsed = json.loads(first_question)
    assert "Hello" not in parsed["display"]
    assert "Привет" not in parsed["display"]
    assert "欢迎参加西电的面试" in parsed["display"]
    assert "Hello" not in parsed["spoken"]
    assert "Привет" not in parsed["spoken"]


def test_chinese_cleanup_removes_trailing_punctuation_garbage():
    cleaned = llm_agent._ensure_text_language(
        "你好！欢迎参加西电的面试。首先，请简单介绍一下你自己。 ! ' . , , , . .",
        "zh",
        "兜底问题",
    )

    assert cleaned == "你好！欢迎参加西电的面试。首先，请简单介绍一下你自己。"


def test_english_cleanup_removes_trailing_punctuation_garbage():
    cleaned = llm_agent._ensure_text_language(
        "Hello! Welcome to the interview. First, please introduce yourself. ! ' . , , , . .",
        "en",
        "Fallback question.",
    )

    assert cleaned == "Hello! Welcome to the interview. First, please introduce yourself."


def test_question_sequence_translates_to_selected_english(monkeypatch):
    fake_llm = FakeLLM(
        [
            "Please explain why you chose to study at Xidian University.",
            "Please describe your academic background and the learning methods you are best at.",
            "Please talk about your understanding of the major you are applying for and your future study plan.",
            "If you study in a new cultural environment, how will you adapt and communicate with others?",
            "Please share an experience that shows your overall qualities or problem-solving ability.",
        ]
    )
    monkeypatch.setattr(llm_agent, "llm", fake_llm)
    monkeypatch.setattr(llm_agent, "load_questions", _fixed_questions)
    monkeypatch.setattr(llm_agent.random, "choice", lambda seq: seq[0])

    questions = llm_agent._build_question_sequence("en")

    assert questions[0].startswith("Hello! Welcome")
    assert all(not any("\u4e00" <= ch <= "\u9fff" for ch in question) for question in questions)
