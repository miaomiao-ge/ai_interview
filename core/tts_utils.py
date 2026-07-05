import http.client
import json
import os
import time
import urllib.error
import urllib.request

from core.config import ALI_APPKEY, get_aliyun_token


def _tts_filename(session_id: str) -> str:
    return f"tts_{session_id}_{int(time.time() * 1000)}.wav"


def _save_tts_audio_locally(audio_bytes: bytes, filename: str) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tts_dir = os.path.join(base_dir, "media", "tts")
    os.makedirs(tts_dir, exist_ok=True)

    filepath = os.path.join(tts_dir, filename)
    with open(filepath, "wb") as file:
        file.write(audio_bytes)
    return f"/media/tts/{filename}"


def generate_tts_audio(text: str, session_id: str, language: str = "zh", max_retries: int = 3) -> str:
    """Call Aliyun TTS and return a local temporary playback URL."""
    token = get_aliyun_token()
    if not token:
        print("⚠️ 无法获取阿里云 Token，TTS 失败", flush=True)
        return ""

    url = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts"
    payload = {
        "appkey": ALI_APPKEY,
        "token": token,
        "text": text,
        "format": "wav",
        "sample_rate": 16000,
    }

    data = json.dumps(payload).encode("utf-8")
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with opener.open(req, timeout=20) as response:
                if response.status != 200:
                    print(f"❌ 阿里云 TTS 请求失败，状态码: {response.status}", flush=True)
                    return ""

                audio_bytes = response.read()
                if not audio_bytes:
                    raise ValueError("阿里云 TTS 返回了空音频")

                filename = _tts_filename(session_id)
                audio_url = _save_tts_audio_locally(audio_bytes, filename)
                print("🔊 阿里云 TTS 生成成功，本地返回", flush=True)
                return audio_url

        except (http.client.IncompleteRead, TimeoutError, urllib.error.URLError) as exc:
            if attempt < max_retries:
                print(f"⚠️ 阿里云 TTS 第 {attempt} 次请求中断，准备重试: {exc}", flush=True)
                time.sleep(0.6 * attempt)
                continue
            print(f"❌ 阿里云 TTS 网络连接异常: {exc}", flush=True)
        except Exception as exc:
            if attempt < max_retries:
                print(f"⚠️ 阿里云 TTS 第 {attempt} 次发生异常，准备重试: {exc}", flush=True)
                time.sleep(0.6 * attempt)
                continue
            print(f"❌ 阿里云 TTS 发生未知异常: {exc}", flush=True)

    return ""
