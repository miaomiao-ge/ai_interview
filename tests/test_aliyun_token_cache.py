import json
from types import SimpleNamespace

import core.config as config


class FakeRequest:
    def set_method(self, *args):
        pass

    def set_domain(self, *args):
        pass

    def set_version(self, *args):
        pass

    def set_action_name(self, *args):
        pass


def make_client(clock):
    class FakeClient:
        calls = 0

        def __init__(self, *args):
            pass

        def do_action_with_exception(self, request):
            FakeClient.calls += 1
            return json.dumps(
                {"Token": {"Id": f"token-{FakeClient.calls}", "ExpireTime": clock[0] + 3600}}
            )

    return FakeClient


def setup_module(module):
    module.clock = [1_700_000_000.0]


def reset_cache():
    config._cached_token = None
    config._cached_token_expires_at = 0.0


def test_cached_token_is_reused_before_expiry(monkeypatch):
    reset_cache()
    client = make_client(clock)
    monkeypatch.setattr(config, "AcsClient", client)
    monkeypatch.setattr(config, "CommonRequest", FakeRequest)
    monkeypatch.setattr(config, "time", SimpleNamespace(time=lambda: clock[0]))

    assert config.get_aliyun_token() == "token-1"
    assert config.get_aliyun_token() == "token-1"
    assert client.calls == 1


def test_expired_token_is_refreshed(monkeypatch):
    reset_cache()
    client = make_client(clock)
    monkeypatch.setattr(config, "AcsClient", client)
    monkeypatch.setattr(config, "CommonRequest", FakeRequest)
    monkeypatch.setattr(config, "time", SimpleNamespace(time=lambda: clock[0]))

    assert config.get_aliyun_token() == "token-1"
    clock[0] += 3600 + config._TOKEN_REFRESH_MARGIN_SECONDS + 1
    assert config.get_aliyun_token() == "token-2"
    assert client.calls == 2


def test_failed_refresh_clears_cache(monkeypatch):
    reset_cache()
    config._cached_token = "expired-token"
    config._cached_token_expires_at = 1.0

    class FailingClient:
        calls = 0

        def __init__(self, *args):
            pass

        def do_action_with_exception(self, request):
            FailingClient.calls += 1
            raise RuntimeError("network down")

    monkeypatch.setattr(config, "AcsClient", FailingClient)
    monkeypatch.setattr(config, "CommonRequest", FakeRequest)
    monkeypatch.setattr(config, "time", SimpleNamespace(time=lambda: clock[0]))

    assert config.get_aliyun_token() == ""
    assert config._cached_token is None
    assert config._cached_token_expires_at == 0.0


def test_appkey_selection_by_language(monkeypatch):
    monkeypatch.setattr(config, "ALI_APPKEY", "zh-key")
    monkeypatch.setattr(config, "ALI_APPKEY_EN", "en-key")
    assert config.get_aliyun_appkey("en") == "en-key"
    assert config.get_aliyun_appkey("en-US") == "en-key"
    assert config.get_aliyun_appkey("zh") == "zh-key"

    monkeypatch.setattr(config, "ALI_APPKEY_EN", "")
    assert config.get_aliyun_appkey("en") == "zh-key"
