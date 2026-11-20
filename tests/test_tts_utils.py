import sys
from pathlib import Path
from types import SimpleNamespace
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("aliyunsdkcore.client", SimpleNamespace(AcsClient=object))
sys.modules.setdefault("aliyunsdkcore.request", SimpleNamespace(CommonRequest=object))

from core import tts_utils


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b"fake-wav"


class FakeOpener:
    def open(self, req, timeout):
        return FakeResponse()


class CapturingOpener(FakeOpener):
    def __init__(self):
        self.payload = None

    def open(self, req, timeout):
        self.payload = json.loads(req.data.decode("utf-8"))
        return FakeResponse()


def test_generate_tts_audio_returns_local_media_url(monkeypatch):
    monkeypatch.setattr(tts_utils, "get_aliyun_token", lambda: "token")
    monkeypatch.setattr(tts_utils.urllib.request, "build_opener", lambda proxy_handler: FakeOpener())
    monkeypatch.setattr(tts_utils, "_save_tts_audio_locally", lambda data, filename: f"/media/tts/{filename}")

    url = tts_utils.generate_tts_audio("hello", "session123")

    assert url.startswith("/media/tts/tts_session123_")


def test_generate_tts_audio_does_not_expose_oss_upload_hook():
    assert not hasattr(tts_utils, "upload_bytes_to_oss")


def test_english_tts_uses_english_appkey(monkeypatch):
    opener = CapturingOpener()
    monkeypatch.setattr(tts_utils, "get_aliyun_token", lambda: "token")
    monkeypatch.setattr(
        tts_utils,
        "get_aliyun_appkey",
        lambda language: "ENKEY" if language == "en" else "ZHKEY",
    )
    monkeypatch.setattr(tts_utils.urllib.request, "build_opener", lambda handler: opener)
    monkeypatch.setattr(tts_utils, "_save_tts_audio_locally", lambda data, filename: "/media/tts/x")

    tts_utils.generate_tts_audio("hello", "session123", "en")

    assert opener.payload["appkey"] == "ENKEY"
    assert opener.payload["text"] == "hello"
