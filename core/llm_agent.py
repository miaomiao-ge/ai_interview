import csv
import json
import os
import random
import re
import httpx
from dataclasses import dataclass, field
from threading import RLock
from typing import Optional, Union
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.config import DASHSCOPE_API_KEY, LLM_BASE_URL, SESSION_TTL_SECONDS, WORKER_NODE_ID
from core.concurrency_guard import release_active_session
from core.database import PromptConfig, QuestionBank, SessionLocal
from core.redis_utils import delete_key, json_get, json_set, redis_key

custom_http_client = httpx.Client(trust_env=False)

# 将 custom_http_client 传给 ChatOpenAI，并确保模型名字是 qwen-max
llm = ChatOpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url=LLM_BASE_URL,
    model="qwen3-max",
    temperature=0.7,
    http_client=custom_http_client  #让大模型请求绕过代理！
)


@dataclass
class InterviewSessionState:
    session_id: str
    language: str
    current_questions: list[str] = field(default_factory=list)
    interview_memory: list = field(default_factory=list)
    question_count: int = 0
    transcript: str = ""
    status: str = "created"
    worker_node_id: str = ""
    media: dict = field(default_factory=dict)
    runtime: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "language": self.language,
            "current_questions": self.current_questions,
            "interview_memory": [_message_to_payload(message) for message in self.interview_memory],
            "question_count": self.question_count,
            "transcript": self.transcript,
            "status": self.status,
            "worker_node_id": self.worker_node_id,
            "media": self.media,
            "runtime": self.runtime,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewSessionState":
        return cls(
            session_id=str(data.get("session_id", "")),
            language=str(data.get("language", "zh")),
            current_questions=list(data.get("current_questions") or []),
            interview_memory=[
                _message_from_payload(item)
                for item in data.get("interview_memory", [])
                if isinstance(item, dict)
            ],
            question_count=int(data.get("question_count") or 0),
            transcript=str(data.get("transcript", "")),
            status=str(data.get("status", "created")),
            worker_node_id=str(data.get("worker_node_id", "")),
            media=dict(data.get("media") or {}),
            runtime=dict(data.get("runtime") or {}),
        )


_session_store: dict[str, InterviewSessionState] = {}
_session_lock = RLock()
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_ENGLISH_RE = re.compile(r"[A-Za-z]")
_ZH_PUNCTUATION = set("，。！？；：、“”‘’（）【】《》、·—…0123456789-_/ ")
_EN_PUNCTUATION = set(".,!?;:()[]{}<>\"'0123456789-_/ ")


def _message_to_payload(message) -> dict:
    class_name = message.__class__.__name__.lower()
    if "system" in class_name:
        role = "system"
    elif "ai" in class_name:
        role = "ai"
    else:
        role = "human"
    return {"role": role, "content": getattr(message, "content", "")}


def _message_from_payload(payload: dict):
    role = payload.get("role")
    content = payload.get("content", "")
    if role == "system":
        return SystemMessage(content=content)
    if role == "ai":
        return AIMessage(content=content)
    return HumanMessage(content=content)


def _session_redis_key(session_id: str) -> str:
    return redis_key("session", session_id, "state")

DEFAULT_LANGUAGE_FALLBACK_QUESTIONS = {
    "个人基本情况与留学动机": {
        "zh": "请介绍一下你选择来西安电子科技大学学习的原因。",
        "en": "Please explain why you chose to study at Xidian University.",
    },
    "学术背景与学习能力": {
        "zh": "请介绍一下你的学术背景，以及你最擅长的学习方式。",
        "en": "Please describe your academic background and the learning methods you are best at.",
    },
    "专业认知与申请规划": {
        "zh": "请谈谈你对所申请专业的理解，以及你的未来学习规划。",
        "en": "Please talk about your understanding of the major you are applying for and your future study plan.",
    },
    "跨文化交流能力": {
        "zh": "如果来到新的文化环境中学习，你会如何适应并与他人沟通？",
        "en": "If you study in a new cultural environment, how will you adapt and communicate with others?",
    },
    "综合素质": {
        "zh": "请分享一个能体现你综合素质或解决问题能力的经历。",
        "en": "Please share an experience that shows your overall qualities or problem-solving ability.",
    },
}

# ==========================================
# 面试官性格与流程基础提示词模板
# ==========================================
DEFAULT_BASE_PROMPT = """你现在是西安电子科技大学（西电）的资深面试官，正在对候选人进行线上面试。
你的回复必须严格遵守以下规则：
1. 必须高度口语化，像真人聊天，绝不输出 Markdown 格式。
2. 每次回复请控制在 50 个字左右，保持精炼，不要长篇大论。
3. 严格遵守我随候选人回答发送的【系统强制指令】来提出题库中指定的下一个问题。"""

# ==========================================
# 面试结束后量化评分提示词模板
# ==========================================
DEFAULT_EVAL_PROMPT = """你现在是一位资深的大学招生官。
请根据以下完整的面试对话记录，对候选人进行合理、稳定、鼓励真实表达的量化打分与客观评价。

【面试对话记录】：
{transcript}

请按照以下评分标准（5个维度，每项满分20分，总分100分）进行评分。

【整体评分校准】：
1. 本面试用于判断候选人的基本匹配度、学习潜力、表达状态和培养价值，不应以专家级、竞赛级、职业化表达作为高分门槛。
2. 候选人只要回答真诚、内容相关、能体现基本理解和学习潜力，即可获得中高分。
3. 认真作答、表达基本完整、态度积极但不够深入的候选人，综合分通常应在 75-85 分之间。
4. 回答具体、有例子、有清晰动机或规划，但仍存在少量表达不足的候选人，可以给到 85-92 分。
5. 只有在回答非常深入、匹配度突出、表达成熟且多维度表现优秀时，才给 92 分以上。
6. 除非出现明显空答、严重跑题、态度消极、无法交流或多题无效回答，否则不要给过低分。

【评分细则】：
每个维度请按以下区间给出具体分数：
- 18-20分：表现优秀，回答具体、真诚、有清晰例子或思考，不要求完美。
- 15-17分：表现良好，内容基本完整，能体现潜力、匹配度或积极态度，可有少量不足。
- 12-14分：表现一般，回答相关但较笼统，深度、结构或细节不足。
- 8-11分：表现较弱，回答不充分、明显缺少理解、表达不清或需要较多引导。
- 0-7分：无效回答、严重跑题、拒答、态度消极或基本无法交流。

具体维度说明：
1. 自我介绍与表达：关注表达是否清楚、回答是否完整、是否能抓住重点。普通但认真完整的表达不应低于15分。
2. 专业匹配度：关注对学校/专业的基本了解、过往背景与申请方向的关联、学习潜力。不要求候选人达到专家水平。
3. 学习动机与规划：关注动机是否真实、目标是否大致清晰、是否有继续学习的意愿。规划不完美但真诚可给中高分。
4. 综合素养与适应能力：关注态度、礼貌、抗压、跨文化适应、合作意识和解决问题倾向。表现稳定积极即可给良好分。
5. 语言能力：关注是否能完成基本交流。允许少量语法、用词或口音问题；只要不影响理解，不应过度扣分。

请严格输出 JSON，不要输出 Markdown，不要输出额外说明，格式如下：
{
  "candidate_name": "候选人姓名或未知",
  "language": "zh",
  "total_score": 0,
  "dimension_scores": [
    {"name": "自我介绍与表达", "score": 0, "comment": "简评"},
    {"name": "专业匹配度", "score": 0, "comment": "简评"},
    {"name": "学习动机与规划", "score": 0, "comment": "简评"},
    {"name": "综合素养与适应能力", "score": 0, "comment": "简评"},
    {"name": "语言能力", "score": 0, "comment": "简评"}
  ],
  "strengths": ["优势1", "优势2"],
  "improvements": ["建议1", "建议2"],
  "summary": "整体总结"
}
"""


def _safe_close_db(db) -> None:
    if db and hasattr(db, "close"):
        db.close()


def _contains_chinese(text: str) -> bool:
    return bool(_CHINESE_RE.search(text or ""))


def _contains_english(text: str) -> bool:
    return bool(_ENGLISH_RE.search(text or ""))


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _remove_punctuation_only_tokens(text: str, lang: str) -> str:
    if not text:
        return ""

    cleaned_tokens = []
    for token in text.split():
        if lang == "zh":
            is_meaningful = _contains_chinese(token) or any(char.isdigit() for char in token)
        else:
            is_meaningful = _contains_english(token) or any(char.isdigit() for char in token)

        if is_meaningful:
            cleaned_tokens.append(token)

    cleaned = " ".join(cleaned_tokens)
    if lang == "zh":
        cleaned = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)
        cleaned = re.sub(r"\s*([，。！？；：])\s*", r"\1", cleaned)
    else:
        cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)

    return _normalize_whitespace(cleaned)


def _filter_text_by_language(text: str, lang: str) -> str:
    if not text:
        return ""

    if lang == "zh":
        filtered = "".join(
            char
            for char in text
            if _contains_chinese(char) or char.isspace() or char in _ZH_PUNCTUATION
        )
        return _remove_punctuation_only_tokens(filtered, lang)

    filtered = "".join(
        char
        for char in text
        if (ord(char) < 128 and (char.isalpha() or char.isspace() or char in _EN_PUNCTUATION))
    )
    return _remove_punctuation_only_tokens(filtered, lang)


def _ensure_text_language(text: str, lang: str, fallback_text: str) -> str:
    filtered = _filter_text_by_language(text, lang)
    if lang == "zh":
        return filtered if _contains_chinese(filtered) else fallback_text
    return filtered if _contains_english(filtered) else fallback_text


def _translate_text_to_language(source_text: str, lang: str, fallback_text: str) -> str:
    if not source_text:
        return fallback_text

    if lang == "zh" and _contains_chinese(source_text) and not _contains_english(source_text):
        return source_text
    if lang == "en" and _contains_english(source_text) and not _contains_chinese(source_text):
        return source_text

    target_label = "中文" if lang == "zh" else "English"
    prompt = (
        f"Translate the following interview question into {target_label}. "
        f"Return only the translated question with no explanations:\n{source_text}"
    )

    try:
        response = llm.invoke([SystemMessage(content=prompt)])
        translated = _ensure_text_language(response.content.strip(), lang, fallback_text)
        return translated or fallback_text
    except Exception:
        return fallback_text


def _sanitize_reply_payload(raw_text: str, lang: str, fallback_display: str, fallback_spoken: Optional[str] = None) -> str:
    fallback_spoken = fallback_spoken or fallback_display
    try:
        parsed = json.loads(raw_text.replace("```json", "").replace("```", "").strip())
    except Exception:
        parsed = {}

    display_text = str(parsed.get("display", parsed.get("spoken", fallback_display))).strip()
    spoken_text = str(parsed.get("spoken", parsed.get("display", fallback_spoken))).strip()

    display_text = _ensure_text_language(display_text, lang, fallback_display)
    spoken_text = _ensure_text_language(spoken_text, lang, fallback_spoken)

    return json.dumps({"spoken": spoken_text, "display": display_text}, ensure_ascii=False)


def load_runtime_prompts() -> tuple[str, str]:
    base_prompt = DEFAULT_BASE_PROMPT
    eval_prompt = DEFAULT_EVAL_PROMPT
    db = SessionLocal()
    if db is None:
        return base_prompt, eval_prompt

    try:
        base = db.query(PromptConfig).filter(PromptConfig.config_key == "base_prompt").first()
        eval_conf = db.query(PromptConfig).filter(PromptConfig.config_key == "eval_prompt").first()
        if base and getattr(base, "config_value", "").strip():
            base_prompt = base.config_value.strip()
        if eval_conf and getattr(eval_conf, "config_value", "").strip():
            eval_prompt = eval_conf.config_value.strip()
    except Exception:
        pass
    finally:
        _safe_close_db(db)

    return base_prompt, eval_prompt


def load_questions():
    db = SessionLocal()
    categories = {
        "个人基本情况与留学动机": [],
        "学术背景与学习能力": [],
        "专业认知与申请规划": [],
        "跨文化交流能力": [],
        "综合素质": [],
    }
    try:
        questions = db.query(QuestionBank).all()
        if not questions:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            csv_path = os.path.join(base_dir, "questions.csv")
            if os.path.exists(csv_path):
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    next(reader, None)
                    for row in reader:
                        if len(row) >= 3 and row[2].strip():
                            cat = row[0].strip()
                            q = row[2].strip()
                            if "介绍一下你自己" not in q and cat in categories:
                                db.add(QuestionBank(category=cat, content=q))
                db.commit()
                questions = db.query(QuestionBank).all()
        for q in questions:
            if q.category in categories:
                categories[q.category].append(q.content)
        if not categories["综合素质"]:
            categories["综合素质"].append("你如何平衡学习和课余生活？")
        return categories
    finally:
        _safe_close_db(db)


def session_exists(session_id: str) -> bool:
    if json_get(_session_redis_key(session_id)):
        return True
    with _session_lock:
        return session_id in _session_store


def update_session_runtime(
    session_id: str,
    status: str = "",
    worker_node_id: str = "",
    media: Optional[dict] = None,
    **runtime_updates,
) -> bool:
    state = _get_session_state(session_id)
    if not state:
        return False
    if status:
        state.status = status
    if worker_node_id:
        state.worker_node_id = worker_node_id
    if media:
        state.media.update(media)
    if runtime_updates:
        state.runtime.update(runtime_updates)
    _save_session_state(state)
    return True


def get_session_media(session_id: str) -> dict:
    state = _get_session_state(session_id)
    if not state:
        return {}
    return dict(state.media or {})


def get_session_snapshot(session_id: str) -> dict:
    state = _get_session_state(session_id)
    return state.to_dict() if state else {}


def restore_session_snapshot(snapshot: dict) -> bool:
    if not isinstance(snapshot, dict) or not snapshot.get("session_id"):
        return False
    state = InterviewSessionState.from_dict(snapshot)
    _save_session_state(state)
    return True


def clear_interview_session(session_id: str) -> None:
    delete_key(_session_redis_key(session_id))
    release_active_session(session_id)
    with _session_lock:
        _session_store.pop(session_id, None)


def _get_session_state(session_id: str) -> Optional[InterviewSessionState]:
    redis_state = json_get(_session_redis_key(session_id))
    if redis_state:
        try:
            return InterviewSessionState.from_dict(redis_state)
        except Exception:
            pass
    with _session_lock:
        return _session_store.get(session_id)


def _save_session_state(state: InterviewSessionState) -> None:
    if json_set(_session_redis_key(state.session_id), state.to_dict(), SESSION_TTL_SECONDS):
        with _session_lock:
            _session_store.pop(state.session_id, None)
        return
    with _session_lock:
        _session_store[state.session_id] = state


def _build_question_sequence(lang: str) -> list[str]:
    categories_dict = load_questions()
    first_q_zh = "你好！欢迎参加西电的面试。首先，请简单介绍一下你自己，包括你的国籍、毕业院校以及个人兴趣爱好。"
    first_q_en = "Hello! Welcome to the Xidian University interview. First, please briefly introduce yourself, including your nationality, graduated school, and personal hobbies."
    first_q = first_q_zh if lang == "zh" else first_q_en

    question_sequence = [first_q]
    for cat in ["个人基本情况与留学动机", "学术背景与学习能力", "专业认知与申请规划", "跨文化交流能力", "综合素质"]:
        if categories_dict[cat]:
            selected_question = random.choice(categories_dict[cat])
            fallback_question = DEFAULT_LANGUAGE_FALLBACK_QUESTIONS[cat][lang]
            question_sequence.append(_translate_text_to_language(selected_question, lang, fallback_question))
    return question_sequence


def _build_session_prompt(lang: str, base_prompt: str, first_question: str) -> tuple[str, str, str]:
    if lang == "zh":
        sys_prompt = base_prompt + """
        \n\n【最高指令】：当前的面试语言是【纯中文】。你的所有回复内容必须 100% 使用中文！绝对不能包含任何英文字符。
        严格输出 JSON 格式：{"spoken": "口语化提问...", "display": "显示文字..."}"""
        display_text = "面试官你好，我已经准备好了，可以开始面试了。"
        instruction = f"\n\n【系统强制指令】：请向我提出第1个问题：【{first_question}】。"
        return sys_prompt, display_text, instruction

    sys_prompt = base_prompt + """
        \n\n[CRITICAL DIRECTIVE]: The current interview language is PURE ENGLISH. ALL your responses MUST be 100% in English! DO NOT output ANY Chinese characters!
        Output ONLY a valid JSON string: {"spoken": "spoken question...", "display": "display text..."}"""
    display_text = "Hello interviewer, I am ready to start the interview."
    instruction = f"\n\n[SYSTEM DIRECTIVE]: Please ask me the first question: [{first_question}]."
    return sys_prompt, display_text, instruction


def create_interview_session(lang: str = "zh", session_id: Optional[str] = None) -> tuple[str, str]:
    session_id = session_id or uuid4().hex[:8]
    question_sequence = _build_question_sequence(lang)
    first_question = question_sequence[0]
    base_prompt, _ = load_runtime_prompts()
    sys_prompt, display_text, instruction = _build_session_prompt(lang, base_prompt, first_question)

    state = InterviewSessionState(
        session_id=session_id,
        language=lang,
        current_questions=question_sequence,
        interview_memory=[
            SystemMessage(content=sys_prompt),
            HumanMessage(content=f"{display_text}{instruction}"),
        ],
        question_count=1,
        status="created",
        worker_node_id=WORKER_NODE_ID,
    )

    try:
        response = llm.invoke(state.interview_memory)
        reply_text = _sanitize_reply_payload(response.content, lang, first_question)
    except Exception:
        reply_text = json.dumps({"spoken": first_question, "display": first_question}, ensure_ascii=False)

    state.interview_memory[-1] = HumanMessage(content=display_text)
    state.interview_memory.append(AIMessage(content=reply_text))
    _save_session_state(state)
    return session_id, reply_text


def generate_interview_response(session_id: str, candidate_text: str) -> dict:
    state = _get_session_state(session_id)
    if not state:
        return {
            "text": json.dumps({"spoken": "会话不存在，请重新开始面试。", "display": "会话不存在，请重新开始面试。"}, ensure_ascii=False),
            "is_end": True,
        }

    if state.question_count >= 6:
        end_msg = (
            "非常感谢你的耐心解答，你的表现很不错，后续会有老师与你联系，再见！"
            if state.language == "zh"
            else "Thank you very much for your patience. Your performance was excellent. Our admissions office will contact you later. Goodbye!"
        )
        state.interview_memory.append(HumanMessage(content=candidate_text))
        state.interview_memory.append(AIMessage(content=json.dumps({"spoken": end_msg, "display": end_msg}, ensure_ascii=False)))
        state.transcript = _build_transcript(state)
        state.status = "ending"
        _save_session_state(state)
        return {"text": json.dumps({"spoken": end_msg, "display": end_msg}, ensure_ascii=False), "is_end": True}

    next_q = state.current_questions[state.question_count]
    if state.language == "zh":
        instruction = f"\n\n【系统强制指令】：这是我的回答，请给出简短反馈，并向我提出下一个问题：【{next_q}】。必须 100% 使用【纯中文】输出 JSON！"
        fallback_reply = f"感谢你的回答。下一个问题：{next_q}"
    else:
        instruction = f"\n\n[SYSTEM DIRECTIVE]: This is my answer. Please provide brief feedback and ask the next question: [{next_q}]. (Translate the question if it's not in English). You MUST output in PURE ENGLISH JSON format without ANY Chinese characters!"
        fallback_reply = f"Thank you for your answer. Next question: {next_q}"

    state.interview_memory.append(HumanMessage(content=f"{candidate_text}{instruction}"))

    try:
        response = llm.invoke(state.interview_memory)
        reply_text = _sanitize_reply_payload(response.content, state.language, fallback_reply)
        state.interview_memory[-1] = HumanMessage(content=candidate_text)
        state.interview_memory.append(AIMessage(content=reply_text))
        state.question_count += 1
        state.status = "waiting_next_answer"
        _save_session_state(state)
        return {"text": reply_text, "is_end": False}
    except Exception as e:
        import traceback
        print(f"\n❌ [致命错误] 大模型调用或解析失败: {e}")
        print(traceback.format_exc())

        if len(state.interview_memory) > 1:
            state.interview_memory.pop()
        err_msg = "抱歉，网络卡顿，能重新说一下吗？" if state.language == "zh" else "Sorry, network lag, could you repeat?"
        _save_session_state(state)
        return {"text": json.dumps({"spoken": err_msg, "display": err_msg}, ensure_ascii=False), "is_end": False}


def _build_transcript(state: InterviewSessionState) -> str:
    transcript = ""
    for msg in state.interview_memory:
        if isinstance(msg, HumanMessage) and "【系统强制指令】" not in msg.content and "[SYSTEM DIRECTIVE]" not in msg.content:
            transcript += f"候选人: {msg.content}\n\n"
        elif isinstance(msg, AIMessage):
            try:
                clean_text = msg.content.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(clean_text)
                transcript += f"面试官: {parsed.get('display', parsed.get('spoken', msg.content))}\n\n"
            except Exception:
                transcript += f"面试官: {msg.content}\n\n"
    return transcript


def _load_json_object(raw_text: str) -> dict:
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            data, _ = decoder.raw_decode(cleaned[match.start():])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    raise ValueError("No valid JSON object found in evaluation response")


def _get_first_present(data: dict, keys: list[str], default=None):
    for key in keys:
        if key in data:
            return data[key]
    return default


def _normalize_evaluation_payload(data: dict) -> dict:
    required_keys = {
        "candidate_name",
        "language",
        "total_score",
        "dimension_scores",
        "strengths",
        "improvements",
        "summary",
    }
    if required_keys.issubset(data.keys()):
        return data

    total_score = _get_first_present(data, ["total_score", "\u7efc\u5408\u5f97\u5206"])
    dimension_source = _get_first_present(data, ["dimension_scores", "\u5404\u9879\u5f97\u5206\u4e0e\u8bc4\u4ef7"])
    strengths = _get_first_present(data, ["strengths", "\u6838\u5fc3\u4f18\u52bf"], [])
    improvements = _get_first_present(data, ["improvements", "\u6539\u8fdb\u5efa\u8bae"], [])
    summary = _get_first_present(data, ["summary", "\u603b\u7ed3"], "")
    candidate_name = _get_first_present(data, ["candidate_name", "\u5019\u9009\u4eba\u59d3\u540d"], "\u672a\u77e5")
    language = _get_first_present(data, ["language", "\u8bed\u8a00"], "zh")

    dimensions = []
    if isinstance(dimension_source, dict):
        for name, item in dimension_source.items():
            if isinstance(item, dict):
                dimensions.append(
                    {
                        "name": name,
                        "score": _get_first_present(item, ["score", "\u5f97\u5206"], 0),
                        "comment": _get_first_present(item, ["comment", "\u7b80\u8bc4", "\u8bc4\u4ef7"], ""),
                    }
                )
            else:
                dimensions.append({"name": name, "score": 0, "comment": str(item)})
    elif isinstance(dimension_source, list):
        for item in dimension_source:
            if isinstance(item, dict):
                dimensions.append(
                    {
                        "name": _get_first_present(item, ["name", "\u540d\u79f0", "\u7ef4\u5ea6"], ""),
                        "score": _get_first_present(item, ["score", "\u5f97\u5206"], 0),
                        "comment": _get_first_present(item, ["comment", "\u7b80\u8bc4", "\u8bc4\u4ef7"], ""),
                    }
                )

    if not summary and dimensions:
        summary = "\u6a21\u578b\u672a\u8fd4\u56de\u603b\u7ed3\uff0c\u5df2\u6839\u636e\u5404\u7ef4\u5ea6\u8bc4\u4ef7\u751f\u6210\u7ed3\u6784\u5316\u62a5\u544a\u3002"

    normalized = {
        "candidate_name": candidate_name,
        "language": language,
        "total_score": total_score,
        "dimension_scores": dimensions,
        "strengths": strengths,
        "improvements": improvements,
        "summary": summary,
    }
    return normalized


def parse_structured_evaluation(raw_text: str) -> dict:
    data = _normalize_evaluation_payload(_load_json_object(raw_text))

    required_keys = {
        "candidate_name",
        "language",
        "total_score",
        "dimension_scores",
        "strengths",
        "improvements",
        "summary",
    }
    missing_keys = sorted(required_keys.difference(data.keys()))
    if missing_keys:
        raise ValueError(f"Missing evaluation keys: {missing_keys}")

    if not isinstance(data["dimension_scores"], list):
        raise ValueError("dimension_scores must be a list")
    if not isinstance(data["strengths"], list):
        raise ValueError("strengths must be a list")
    if not isinstance(data["improvements"], list):
        raise ValueError("improvements must be a list")

    data["total_score"] = int(data["total_score"])
    normalized_dimensions = []
    for item in data["dimension_scores"]:
        normalized_dimensions.append(
            {
                "name": str(item.get("name", "")).strip(),
                "score": int(item.get("score", 0)),
                "comment": str(item.get("comment", "")).strip(),
            }
        )
    data["dimension_scores"] = normalized_dimensions
    data["candidate_name"] = str(data["candidate_name"]).strip() or "未知"
    data["language"] = str(data["language"]).strip() or "zh"
    data["strengths"] = [str(item).strip() for item in data["strengths"] if str(item).strip()]
    data["improvements"] = [str(item).strip() for item in data["improvements"] if str(item).strip()]
    data["summary"] = str(data["summary"]).strip()
    return data


def render_structured_evaluation_report(payload: dict) -> str:
    lines = [
        f"综合得分：{payload['total_score']}/100",
        "",
        "各项得分与评价：",
    ]

    for item in payload["dimension_scores"]:
        lines.append(f"- {item['name']} ({item['score']}/20)：{item['comment']}")

    lines.extend(["", "核心优势："])
    if payload["strengths"]:
        lines.extend(f"- {item}" for item in payload["strengths"])
    else:
        lines.append("- 暂无")

    lines.extend(["", "改进建议："])
    if payload["improvements"]:
        lines.extend(f"- {item}" for item in payload["improvements"])
    else:
        lines.append("- 暂无")

    lines.extend(["", f"总结：{payload['summary']}"])
    return "\n".join(lines)


def _is_no_answer_text(text: str) -> bool:
    normalized = _normalize_whitespace(text).lower()
    if not normalized:
        return True

    no_answer_markers = [
        "no answer",
        "候选人未作答",
    ]
    return any(marker in normalized for marker in no_answer_markers)


def _looks_like_possible_asr_loss(state: InterviewSessionState, candidate_answers: list[str]) -> bool:
    if getattr(state, "language", "") != "en":
        return False
    meaningful_answers = [
        answer
        for answer in candidate_answers
        if answer and not _is_no_answer_text(answer)
    ]
    if not meaningful_answers:
        return False
    total_words = sum(len(re.findall(r"[A-Za-z]+", answer)) for answer in meaningful_answers)
    return total_words <= max(12, len(meaningful_answers) * 6)


def _build_evaluation_guardrails(state: InterviewSessionState, candidate_answers: list[str]) -> str:
    if not _looks_like_possible_asr_loss(state, candidate_answers):
        return ""
    return (
        "\n\n【ASR 保护指令 / possible_asr_loss】:\n"
        "The interview language is English, but the recognized candidate answers are unusually short. "
        "Treat this as possible_asr_loss caused by ASR or audio capture before heavily penalizing language ability."
    )


def _calibrate_evaluation_payload(payload: dict, state: InterviewSessionState, candidate_answers: list[str]) -> dict:
    if not _looks_like_possible_asr_loss(state, candidate_answers):
        return payload

    dimensions = payload.get("dimension_scores")
    if not isinstance(dimensions, list):
        return payload

    for item in dimensions:
        name = str(item.get("name", "")).lower()
        if "language" not in name and "语言" not in name:
            continue
        original_score = int(item.get("score", 0) or 0)
        if original_score < 8:
            item["score"] = 8
            comment = str(item.get("comment", "")).strip()
            suffix = "ASR possible_asr_loss noted; language score protected from over-penalization."
            item["comment"] = f"{comment} {suffix}".strip()
        break

    try:
        payload["total_score"] = sum(int(item.get("score", 0) or 0) for item in dimensions)
    except Exception:
        pass
    return payload


def _apply_score_uplift(payload: dict) -> dict:
    dimensions = payload.get("dimension_scores")
    if not isinstance(dimensions, list):
        return payload

    changed = False
    for item in dimensions:
        try:
            score = int(item.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        if 0 < score < 20:
            item["score"] = min(20, score + 1)
            changed = True

    if changed:
        try:
            payload["total_score"] = min(100, sum(int(item.get("score", 0) or 0) for item in dimensions))
        except Exception:
            pass
    return payload


def _candidate_answer_messages(state: InterviewSessionState) -> list[str]:
    answers = []
    seen_ai_question = False
    for msg in state.interview_memory:
        if isinstance(msg, AIMessage):
            seen_ai_question = True
            continue
        if not isinstance(msg, HumanMessage):
            continue
        if not seen_ai_question:
            continue
        if "【系统强制指令】" in msg.content or "[SYSTEM DIRECTIVE]" in msg.content:
            continue
        answers.append(str(msg.content).strip())
    return answers


def _build_no_answer_evaluation(language: str) -> dict:
    dimension_names = [
        "自我介绍与表达",
        "专业匹配度",
        "学习动机与规划",
        "综合素养与适应能力",
        "语言能力",
    ]
    return {
        "candidate_name": "未知",
        "language": language or "zh",
        "total_score": 0,
        "dimension_scores": [
            {
                "name": name,
                "score": 0,
                "comment": "候选人未作答，缺少可评价信息。",
            }
            for name in dimension_names
        ],
        "strengths": [],
        "improvements": ["建议候选人完整回答每一道面试问题，以便招生老师判断真实能力。"],
        "summary": "本次面试中候选人未提供有效回答，系统无法依据内容评估其专业基础、表达能力和学习动机，因此按未作答处理。",
    }


def evaluate_interview(session_id: str) -> Union[dict, str]:
    state = _get_session_state(session_id)
    if not state:
        structured = _build_no_answer_evaluation("zh")
        structured["summary"] = "未找到面试会话状态，系统按未完整作答处理。"
        report = render_structured_evaluation_report(structured)
        return {"report": report, "structured": structured}

    state.status = "evaluating"
    state.transcript = _build_transcript(state)
    _save_session_state(state)
    if len(state.interview_memory) <= 3:
        structured = _build_no_answer_evaluation(state.language)
        structured["summary"] = "本次面试有效作答记录不足，系统按未完整作答处理。"
        report = render_structured_evaluation_report(structured)
        state.status = "evaluated"
        _save_session_state(state)
        return {"report": report, "structured": structured}
    candidate_answers = _candidate_answer_messages(state)
    if candidate_answers and all(_is_no_answer_text(answer) for answer in candidate_answers):
        structured = _build_no_answer_evaluation(state.language)
        report = render_structured_evaluation_report(structured)
        state.status = "evaluated"
        _save_session_state(state)
        return {"report": report, "structured": structured}

    _, eval_prompt_template = load_runtime_prompts()
    eval_prompt = eval_prompt_template.replace("{transcript}", state.transcript)
    eval_prompt += _build_evaluation_guardrails(state, candidate_answers)
    eval_prompt += """

【最高审核指令】：
1. 无论上方的面试记录使用的是英文还是中文，你输出的总结内容都必须使用中文。
2. 只允许输出一个合法 JSON 对象，不允许输出 Markdown、代码解释或额外前后缀。
3. dimension_scores 中请覆盖这 5 个维度：自我介绍与表达、专业匹配度、学习动机与规划、综合素养与适应能力、语言能力。
"""

    try:
        response = llm.invoke([SystemMessage(content=eval_prompt)])
        structured = parse_structured_evaluation(response.content)
        structured = _calibrate_evaluation_payload(structured, state, candidate_answers)
        structured = _apply_score_uplift(structured)
        report = render_structured_evaluation_report(structured)
        state.status = "evaluated"
        _save_session_state(state)
        return {"report": report, "structured": structured}
    except Exception as exc:
        print(f"❌ 评估报告生成异常: {type(exc).__name__}: {exc}")
        try:
            print(f"❌ 评估模型原始输出: {getattr(response, 'content', '')}")
        except Exception:
            pass
        _save_session_state(state)
        return "评估报告生成失败 / Evaluation report generation failed."


def get_chat_history_string(session_id: str) -> str:
    state = _get_session_state(session_id)
    if not state:
        return ""
    state.transcript = _build_transcript(state)
    _save_session_state(state)
    return state.transcript
