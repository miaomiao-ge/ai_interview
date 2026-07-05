import json
import threading
import time

import av
import nls

from core.config import (
    ASR_FILE_TIMEOUT_SECONDS,
    ASR_STREAM_SLEEP_SECONDS,
    get_aliyun_asr_appkey,
    get_aliyun_asr_start_options,
    get_aliyun_token,
)


class FileASRCollector:
    def __init__(self):
        self.final_text_parts = []
        self.latest_partial_text = ""
        self.error_message = ""
        self.done = threading.Event()

    def on_start(self, message, *args):
        pass

    def on_sentence_begin(self, message, *args):
        pass

    def on_result_changed(self, message, *args):
        try:
            text = json.loads(message).get("payload", {}).get("result", "")
            if text:
                self.latest_partial_text = text
        except Exception:
            pass

    def on_sentence_end(self, message, *args):
        try:
            text = json.loads(message).get("payload", {}).get("result", "")
            if text:
                self.final_text_parts.append(text)
                self.latest_partial_text = ""
        except Exception:
            pass

    def on_error(self, message, *args):
        self.error_message = str(message)
        self.done.set()

    def on_close(self, *args):
        self.done.set()

    def text(self) -> str:
        return "".join(self.final_text_parts).strip() or self.latest_partial_text.strip()


def iter_media_pcm_chunks(local_file_path: str):
    container = av.open(local_file_path)
    try:
        audio_streams = [stream for stream in container.streams if stream.type == "audio"]
        if not audio_streams:
            return

        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            for resampled_frame in resampler.resample(frame):
                data = resampled_frame.to_ndarray().tobytes()
                if data:
                    yield data
    finally:
        container.close()


def transcribe_media_file(local_file_path: str, language: str = "zh", timeout_seconds: int = ASR_FILE_TIMEOUT_SECONDS) -> str:
    token = get_aliyun_token()
    if not token:
        raise RuntimeError("阿里云 ASR token 获取失败")

    collector = FileASRCollector()
    transcriber = nls.NlsSpeechTranscriber(
        url="wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1",
        appkey=get_aliyun_asr_appkey(language),
        token=token,
        on_start=collector.on_start,
        on_sentence_begin=collector.on_sentence_begin,
        on_result_changed=collector.on_result_changed,
        on_sentence_end=collector.on_sentence_end,
        on_error=collector.on_error,
        on_close=collector.on_close,
    )

    try:
        transcriber.start(**get_aliyun_asr_start_options())
        sent_any_audio = False
        for pcm_data in iter_media_pcm_chunks(local_file_path):
            sent_any_audio = True
            transcriber.send_audio(pcm_data)
            if ASR_STREAM_SLEEP_SECONDS > 0:
                time.sleep(ASR_STREAM_SLEEP_SECONDS)

        if not sent_any_audio:
            raise RuntimeError("上传文件中未检测到音频轨道")

        transcriber.stop()
        collector.done.wait(timeout=timeout_seconds)
        if collector.error_message and not collector.text():
            raise RuntimeError(f"阿里云 ASR 识别失败: {collector.error_message}")
        return collector.text()
    finally:
        try:
            transcriber.stop()
        except Exception:
            pass
