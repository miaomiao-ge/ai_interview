"""Speech provider adapter; all audio stays in memory, no transcript logging."""
import asyncio
import json
import os
import threading
import time
import urllib.request


class Speech:
    def __init__(self):
        self.token = ''
        self.expires = 0
        self.lock = threading.Lock()
        self.audio = {}

    def get_token(self):
        with self.lock:
            if self.token and time.time() < self.expires - 300:
                return self.token
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkcore.request import CommonRequest
            client = AcsClient(os.environ['ALI_AK_ID'], os.environ['ALI_AK_SECRET'], 'cn-shanghai')
            request = CommonRequest()
            request.set_method('POST')
            request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
            request.set_version('2019-02-28')
            request.set_action_name('CreateToken')
            token = json.loads(client.do_action_with_exception(request))['Token']
            self.token = token['Id']
            self.expires = token['ExpireTime']
            return self.token

    def appkey(self, language):
        return (os.getenv('ALI_APPKEY_EN') if language == 'en' else '') or os.environ['ALI_APPKEY']

    def synthesize(self, text, language):
        key = (text, language)
        if key in self.audio:
            return self.audio[key]
        payload = json.dumps({
            'appkey': self.appkey(language), 'token': self.get_token(),
            'text': text, 'format': 'wav', 'sample_rate': 16000,
            'voice': 'siyue' if language == 'zh' else 'cally',
        }).encode()
        req = urllib.request.Request(
            'https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts',
            data=payload, headers={'Content-Type': 'application/json'},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=20) as response:
            audio = response.read(2 * 1024 * 1024)
        if not audio.startswith(b'RIFF'):
            raise RuntimeError('tts_unavailable')
        if len(self.audio) < 12:
            self.audio[key] = audio
        return audio

    def recognizer(self, language, loop, queue):
        return Recognizer(self, language, loop, queue)


class Recognizer:
    def __init__(self, speech, language, loop, queue):
        self.speech, self.language, self.loop, self.queue = speech, language, loop, queue
        self.parts, self.partial = [], ''
        self.transcriber = None
        self.closed = False
        self.error = False

    def emit(self, payload):
        def enqueue():
            if not self.closed:
                if self.queue.full():
                    self.queue.get_nowait()
                self.queue.put_nowait(payload)
        if not self.closed:
            self.loop.call_soon_threadsafe(enqueue)

    def on_partial(self, message, *args):
        self.partial = json.loads(message).get('payload', {}).get('result', '')
        self.emit({'type': 'partial', 'text': ''.join(self.parts) + self.partial})

    def on_final(self, message, *args):
        self.parts.append(json.loads(message).get('payload', {}).get('result', ''))
        self.partial = ''
        self.emit({'type': 'partial', 'text': ''.join(self.parts)})

    def on_error(self, message, *args):
        self.error = True
        self.emit({'type': 'error', 'code': 'asr_unavailable'})

    def start(self):
        import nls
        self.transcriber = nls.NlsSpeechTranscriber(
            url='wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1',
            appkey=self.speech.appkey(self.language), token=self.speech.get_token(),
            on_result_changed=self.on_partial, on_sentence_end=self.on_final,
            on_error=self.on_error,
        )
        self.transcriber.start(aformat='pcm', sample_rate=16000, ch=1,
            enable_intermediate_result=True, enable_punctuation_prediction=True,
            enable_inverse_text_normalization=True, timeout=10, ping_interval=8)
        if self.error:
            raise RuntimeError('asr_unavailable')

    def send(self, data):
        self.transcriber.send_audio(data)

    def finish(self):
        self.stop()
        if self.error:
            raise RuntimeError('asr_unavailable')
        return (''.join(self.parts) or self.partial).strip()

    def stop(self):
        if self.transcriber:
            transcriber, self.transcriber = self.transcriber, None
            transcriber.stop()
