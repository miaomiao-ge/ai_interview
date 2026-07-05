import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("aliyunsdkcore.client", SimpleNamespace(AcsClient=object))
sys.modules.setdefault("aliyunsdkcore.request", SimpleNamespace(CommonRequest=object))

from core import concurrency_guard as guard


def _reset_local_state(monkeypatch, session_limit=2, asr_limit=1):
    monkeypatch.setattr(guard, "get_redis_client", lambda: None)
    monkeypatch.setattr(guard, "MAX_ACTIVE_INTERVIEWS", session_limit)
    monkeypatch.setattr(guard, "MAX_ACTIVE_ASR_CONNECTIONS", asr_limit)
    with guard._local_lock:
        guard._local_active["sessions"].clear()
        guard._local_active["asr"].clear()


def test_active_session_limit_and_release(monkeypatch):
    _reset_local_state(monkeypatch, session_limit=2)

    first = guard.try_register_active_session("s1")
    second = guard.try_register_active_session("s2")
    third = guard.try_register_active_session("s3")

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.active_count == 2

    guard.release_active_session("s1")
    assert guard.try_register_active_session("s3").allowed is True


def test_asr_connection_limit_and_idempotent_member(monkeypatch):
    _reset_local_state(monkeypatch, asr_limit=1)

    first = guard.try_register_active_asr("s1:conn")
    repeat = guard.try_register_active_asr("s1:conn")
    second = guard.try_register_active_asr("s2:conn")

    assert first.allowed is True
    assert repeat.allowed is True
    assert second.allowed is False

    guard.release_active_asr("s1:conn")
    assert guard.try_register_active_asr("s2:conn").allowed is True
