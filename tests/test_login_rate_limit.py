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
sys.modules.setdefault("aliyunsdkcore.client", SimpleNamespace(AcsClient=object))
sys.modules.setdefault("aliyunsdkcore.request", SimpleNamespace(CommonRequest=object))
sys.modules.setdefault(
    "oss2",
    SimpleNamespace(
        Auth=lambda *args, **kwargs: None,
        Bucket=lambda *args, **kwargs: SimpleNamespace(
            put_object_from_file=lambda *call_args, **call_kwargs: None,
            put_object=lambda *call_args, **call_kwargs: None,
        ),
    ),
)

from routers import admin_api, user_api


def test_user_login_limit_counts_failures_only(monkeypatch):
    user_api._local_rate_limits.clear()
    monkeypatch.setattr(user_api, "fixed_window_current_count", lambda key: 0)
    monkeypatch.setattr(user_api, "fixed_window_increment", lambda key, window_seconds: 0)

    key = user_api.redis_key("rate_limit", "login_email", "candidate@example.com")

    for _ in range(user_api.LOGIN_LIMIT_PER_WINDOW * 2):
        assert user_api.is_login_failure_limited(key, user_api.LOGIN_LIMIT_PER_WINDOW) is False

    assert user_api.local_rate_limit_count(key) == 0

    for _ in range(user_api.LOGIN_LIMIT_PER_WINDOW):
        user_api.record_login_failure(key, user_api.LOGIN_RATE_LIMIT_WINDOW_SECONDS)

    assert user_api.is_login_failure_limited(key, user_api.LOGIN_LIMIT_PER_WINDOW) is True

    user_api.clear_rate_limit(key)
    assert user_api.is_login_failure_limited(key, user_api.LOGIN_LIMIT_PER_WINDOW) is False


def test_admin_login_limit_counts_failures_only(monkeypatch):
    admin_api._local_admin_rate_limits.clear()
    monkeypatch.setattr(admin_api, "fixed_window_current_count", lambda key: 0)
    monkeypatch.setattr(admin_api, "fixed_window_increment", lambda key, window_seconds: 0)

    key = admin_api.redis_key("rate_limit", "admin_login_user", "ops")

    for _ in range(admin_api.ADMIN_LOGIN_LIMIT_PER_WINDOW * 2):
        assert admin_api.is_admin_login_failure_limited(key, admin_api.ADMIN_LOGIN_LIMIT_PER_WINDOW) is False

    assert admin_api.local_admin_rate_limit_count(key) == 0

    for _ in range(admin_api.ADMIN_LOGIN_LIMIT_PER_WINDOW):
        admin_api.record_admin_login_failure(key, admin_api.LOGIN_RATE_LIMIT_WINDOW_SECONDS)

    assert admin_api.is_admin_login_failure_limited(key, admin_api.ADMIN_LOGIN_LIMIT_PER_WINDOW) is True

    admin_api.clear_admin_rate_limit(key)
    assert admin_api.is_admin_login_failure_limited(key, admin_api.ADMIN_LOGIN_LIMIT_PER_WINDOW) is False
