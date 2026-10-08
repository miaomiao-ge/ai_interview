import { submitAnswerAPI, submitAnswerMediaAPI, uploadMediaAPI } from './api.js?v=889';

export class InterviewMediaManager {
    constructor() {
        this.localStream = null;
        this.mediaRecorder = null;
        this.recordedChunks = [];
        this.sessionId = "";
        this.language = "zh";
        this.recognition = null;
        this.currentTranscript = "";
        this.browserTranscript = "";
        this.realtimeTranscript = "";
        this.isSubmittingAnswer = false;
        this.answerRecorder = null;
        this.answerChunks = [];
        this.asrWebSocket = null;
        this.asrReplyPromise = null;
        this.asrReplyResolved = false;
        this.answerCaptureActive = false;
        this.isAITTSPlaying = false;
        this.micMuted = false;
        this.ttsPlaybackId = 0;
        this.audioContext = null;
        this.audioSourceNode = null;
        this.audioProcessorNode = null;
        this.silentGainNode = null;
        this.processedAudioStream = null;
        this.micBoostContext = null;
        this.micBoostSource = null;
        this.micBoostGain = null;
        this.micBoostDestination = null;
        this.micGainValue = 2.2;
        this.volumeContext = null;
        this.volumeSource = null;
        this.volumeAnalyser = null;
        this.volumeData = null;
        this.volumeFrame = null;
        this.smoothedVolumeLevel = 0;
        this.audioInputDevices = [];
        this.selectedAudioDeviceId = localStorage.getItem('ai_interviewer_audio_input_id') || "";
        this.selectedAudioDeviceLabel = "";

        this.onQuestionReceived = null;
        this.onTTSStart = null;
        this.onTTSEnd = null;
        this.onInterviewEnd = null;
        this.onAudioDevicesChanged = null;
        this.onAudioInputChanged = null;
        this.onAudioLevel = null;
    }

    async startCamera() {
        await this.openLocalStream(this.selectedAudioDeviceId);
        const devices = await this.refreshAudioInputDevices();
        const preferredDevice = this.pickPreferredAudioInput(devices);
        const currentDeviceId = this.getCurrentAudioDeviceId();

        if (preferredDevice?.deviceId && preferredDevice.deviceId !== currentDeviceId) {
            console.log('[AUDIO][auto_switch_input]', preferredDevice.label || preferredDevice.deviceId);
            await this.openLocalStream(preferredDevice.deviceId);
            await this.refreshAudioInputDevices();
        }

        this.reportSelectedAudioInput();
        return this.audioInputDevices;
    }

    buildMediaConstraints(deviceId = "") {
        const audio = {
            sampleRate: 48000,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
        };
        if (deviceId) {
            audio.deviceId = { exact: deviceId };
        }
        return {
            audio,
            video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 20 } }
        };
    }

    async openLocalStream(deviceId = "") {
        const constraints = this.buildMediaConstraints(deviceId);
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (error) {
            if (!deviceId) {
                throw error;
            }
            console.warn('[AUDIO][device_fallback]', error);
            localStorage.removeItem('ai_interviewer_audio_input_id');
            this.selectedAudioDeviceId = "";
            stream = await navigator.mediaDevices.getUserMedia(this.buildMediaConstraints());
        }

        this.stopRealtimeAudioNodes();
        this.closeBoostedAudioStream();
        if (this.localStream) {
            this.localStream.getTracks().forEach((track) => track.stop());
        }
        this.localStream = stream;
        document.getElementById('localVideo').srcObject = this.localStream;
        this.setupBoostedAudioStream();
        this.startVolumeMonitor();
    }

    async refreshAudioInputDevices() {
        if (!navigator.mediaDevices?.enumerateDevices) {
            this.audioInputDevices = [];
            return [];
        }
        const devices = await navigator.mediaDevices.enumerateDevices();
        this.audioInputDevices = devices.filter((device) => device.kind === 'audioinput');
        if (this.onAudioDevicesChanged) {
            this.onAudioDevicesChanged(this.audioInputDevices);
        }
        return this.audioInputDevices;
    }

    getCurrentAudioDeviceId() {
        return this.localStream?.getAudioTracks()?.[0]?.getSettings?.()?.deviceId || "";
    }

    findDeviceById(deviceId) {
        return this.audioInputDevices.find((device) => device.deviceId === deviceId) || null;
    }

    isHeadsetLikeDevice(device) {
        const label = (device?.label || "").toLowerCase();
        return /hands-free|headset|headphone|earbud|freebuds|airpods|bluetooth|耳机|耳麦/.test(label);
    }

    isBuiltInMicDevice(device) {
        const label = (device?.label || "").toLowerCase();
        return /麦克风阵列|microphone array|digital microphone|内置|built-in|intel/.test(label);
    }

    pickPreferredAudioInput(devices = this.audioInputDevices) {
        if (!devices.length) {
            return null;
        }
        const saved = this.selectedAudioDeviceId
            ? devices.find((device) => device.deviceId === this.selectedAudioDeviceId)
            : null;
        if (saved) {
            return saved;
        }
        return devices.find((device) => this.isHeadsetLikeDevice(device))
            || devices.find((device) => !this.isBuiltInMicDevice(device))
            || devices[0];
    }

    reportSelectedAudioInput() {
        const currentDeviceId = this.getCurrentAudioDeviceId();
        const currentDevice = this.findDeviceById(currentDeviceId);
        this.selectedAudioDeviceId = currentDeviceId;
        this.selectedAudioDeviceLabel = currentDevice?.label || "Default microphone";
        if (currentDeviceId) {
            localStorage.setItem('ai_interviewer_audio_input_id', currentDeviceId);
        }
        console.log('[AUDIO][selected_input]', this.selectedAudioDeviceLabel, currentDeviceId);
        if (this.onAudioInputChanged) {
            this.onAudioInputChanged(currentDevice || {
                deviceId: currentDeviceId,
                label: this.selectedAudioDeviceLabel
            });
        }
    }

    async switchAudioInput(deviceId) {
        if (!deviceId || deviceId === this.getCurrentAudioDeviceId()) {
            return;
        }
        if (this.answerRecorder || this.audioProcessorNode) {
            throw new Error('请在本题未作答时切换麦克风。');
        }

        const wasRecording = !!this.mediaRecorder;
        if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
            const recorder = this.mediaRecorder;
            await new Promise((resolve) => {
                recorder.onstop = resolve;
                recorder.stop();
            });
        }
        this.mediaRecorder = null;
        this.selectedAudioDeviceId = deviceId;
        localStorage.setItem('ai_interviewer_audio_input_id', deviceId);
        await this.openLocalStream(deviceId);
        await this.refreshAudioInputDevices();
        this.reportSelectedAudioInput();
        if (wasRecording) {
            this.startLocalRecording(false);
        }
    }

    async usePreferredAudioInput() {
        const devices = await this.refreshAudioInputDevices();
        const preferred = this.pickPreferredAudioInput(devices);
        if (preferred?.deviceId) {
            await this.switchAudioInput(preferred.deviceId);
        }
    }

    setupBoostedAudioStream() {
        const audioTracks = this.localStream?.getAudioTracks() || [];
        if (!audioTracks.length) {
            this.processedAudioStream = null;
            return;
        }

        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            this.processedAudioStream = new MediaStream(audioTracks);
            return;
        }

        this.closeBoostedAudioStream();
        this.micBoostContext = new AudioContextClass();
        this.micBoostSource = this.micBoostContext.createMediaStreamSource(new MediaStream(audioTracks));
        this.micBoostGain = this.micBoostContext.createGain();
        this.micBoostDestination = this.micBoostContext.createMediaStreamDestination();
        this.micBoostGain.gain.value = this.micGainValue;

        this.micBoostSource.connect(this.micBoostGain);
        this.micBoostGain.connect(this.micBoostDestination);
        this.processedAudioStream = this.micBoostDestination.stream;
        this.micBoostContext.resume().catch(() => {});
        console.log('[AUDIO][mic_gain]', this.micGainValue);
    }

    closeBoostedAudioStream() {
        if (this.processedAudioStream) {
            this.processedAudioStream.getTracks().forEach((track) => track.stop());
            this.processedAudioStream = null;
        }
        if (this.micBoostSource) {
            this.micBoostSource.disconnect();
            this.micBoostSource = null;
        }
        if (this.micBoostGain) {
            this.micBoostGain.disconnect();
            this.micBoostGain = null;
        }
        if (this.micBoostDestination) {
            this.micBoostDestination.disconnect();
            this.micBoostDestination = null;
        }
        if (this.micBoostContext) {
            this.micBoostContext.close().catch(() => {});
            this.micBoostContext = null;
        }
    }

    startVolumeMonitor() {
        this.stopVolumeMonitor();
        const audioTracks = this.localStream?.getAudioTracks() || [];
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!audioTracks.length || !AudioContextClass) {
            if (this.onAudioLevel) {
                this.onAudioLevel({ level: 0, muted: true, available: false });
            }
            return;
        }

        this.volumeContext = new AudioContextClass();
        this.volumeSource = this.volumeContext.createMediaStreamSource(new MediaStream(audioTracks));
        this.volumeAnalyser = this.volumeContext.createAnalyser();
        this.volumeAnalyser.fftSize = 512;
        this.volumeAnalyser.smoothingTimeConstant = 0.72;
        this.volumeData = new Uint8Array(this.volumeAnalyser.fftSize);
        this.volumeSource.connect(this.volumeAnalyser);
        this.volumeContext.resume().catch(() => {});

        const tick = () => {
            if (!this.volumeAnalyser || !this.volumeData) return;
            this.volumeAnalyser.getByteTimeDomainData(this.volumeData);
            let sum = 0;
            for (let i = 0; i < this.volumeData.length; i++) {
                const normalized = (this.volumeData[i] - 128) / 128;
                sum += normalized * normalized;
            }
            const rms = Math.sqrt(sum / this.volumeData.length);
            const audioTrack = this.localStream?.getAudioTracks()?.[0];
            const muted = !audioTrack || audioTrack.enabled === false || audioTrack.readyState !== "live";
            const rawLevel = muted ? 0 : Math.min(1, rms * 3.8);
            this.smoothedVolumeLevel = this.smoothedVolumeLevel * 0.72 + rawLevel * 0.28;
            if (this.onAudioLevel) {
                this.onAudioLevel({
                    level: this.smoothedVolumeLevel,
                    rms,
                    muted,
                    available: true
                });
            }
            this.volumeFrame = window.requestAnimationFrame(tick);
        };

        tick();
    }

    stopVolumeMonitor() {
        if (this.volumeFrame) {
            window.cancelAnimationFrame(this.volumeFrame);
            this.volumeFrame = null;
        }
        if (this.volumeSource) {
            this.volumeSource.disconnect();
            this.volumeSource = null;
        }
        if (this.volumeAnalyser) {
            this.volumeAnalyser.disconnect();
            this.volumeAnalyser = null;
        }
        if (this.volumeContext) {
            this.volumeContext.close().catch(() => {});
            this.volumeContext = null;
        }
        this.volumeData = null;
        this.smoothedVolumeLevel = 0;
        if (this.onAudioLevel) {
            this.onAudioLevel({ level: 0, muted: true, available: false });
        }
    }

    getAudioTracksForCapture() {
        const boostedTracks = this.processedAudioStream?.getAudioTracks() || [];
        if (boostedTracks.length) {
            return boostedTracks;
        }
        return this.localStream?.getAudioTracks() || [];
    }

    getAppBasePath() {
        const path = window.location.pathname || "";
        return path === "/interview" || path.startsWith("/interview/") ? "/interview" : "";
    }

    resolveAppUrl(url) {
        const value = String(url || "").trim();
        if (!value || /^[a-z][a-z0-9+.-]*:/i.test(value)) {
            return value;
        }
        const basePath = this.getAppBasePath();
        if (!basePath || value.startsWith(`${basePath}/`)) {
            return value;
        }
        return value.startsWith("/") ? `${basePath}${value}` : value;
    }

    buildRecordingStream() {
        const stream = new MediaStream();
        this.getAudioTracksForCapture().forEach((track) => stream.addTrack(track));
        (this.localStream?.getVideoTracks() || []).forEach((track) => stream.addTrack(track));
        return stream;
    }

    async connect(language, sessionId) {
        if (!sessionId) {
            throw new Error("缺少面试会话 ID，请重新初始化面试。");
        }
        this.language = language || 'zh';
        this.sessionId = sessionId;
        this.startLocalRecording();
    }

    getRecorderMimeType() {
        const candidates = [
            'video/webm;codecs=vp8,opus',
            'video/webm;codecs=vp9,opus',
            'video/webm'
        ];
        return candidates.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || '';
    }

    getAudioRecorderMimeType() {
        const candidates = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus'
        ];
        return candidates.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || '';
    }

    startLocalRecording(resetChunks = true) {
        if (!this.localStream || !window.MediaRecorder || this.mediaRecorder) {
            return;
        }
        if (resetChunks) {
            this.recordedChunks = [];
        }
        const recordingStream = this.buildRecordingStream();
        if (!recordingStream.getTracks().length) {
            return;
        }
        const mimeType = this.getRecorderMimeType();
        const options = mimeType ? { mimeType } : undefined;
        this.mediaRecorder = new MediaRecorder(recordingStream, options);
        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
                this.recordedChunks.push(event.data);
            }
        };
        this.mediaRecorder.start(1000);
    }

    createSpeechRecognition() {
        const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!Recognition) {
            return null;
        }
        const recognition = new Recognition();
        recognition.lang = this.language === 'en' ? 'en-US' : 'zh-CN';
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.onresult = (event) => {
            if (this.isAITTSPlaying || !this.answerCaptureActive) {
                return;
            }
            let transcript = "";
            for (let index = 0; index < event.results.length; index++) {
                transcript += event.results[index][0].transcript;
            }
            this.browserTranscript = transcript.trim();
            this.currentTranscript = this.pickBetterTranscript(this.currentTranscript, this.browserTranscript);
        };
        recognition.onerror = () => {};
        return recognition;
    }

    pickBetterTranscript(left, right) {
        const a = (left || '').trim();
        const b = (right || '').trim();
        if (!a) return b;
        if (!b) return a;
        if (a.length <= 6 && b.length >= a.length + 3) return b;
        if (b.length <= 6 && a.length >= b.length + 3) return a;
        return b.length > a.length ? b : a;
    }

    getBestTranscript() {
        return [this.currentTranscript, this.browserTranscript, this.realtimeTranscript]
            .reduce((best, item) => this.pickBetterTranscript(best, item), '')
            .trim();
    }

    startAnswerAudioRecording() {
        if (!this.localStream || !window.MediaRecorder || this.isAITTSPlaying || this.answerRecorder) {
            return;
        }
        const audioTracks = this.getAudioTracksForCapture();
        if (!audioTracks.length) {
            return;
        }
        this.answerChunks = [];
        const audioStream = new MediaStream(audioTracks);
        const mimeType = this.getAudioRecorderMimeType();
        const options = mimeType ? { mimeType } : undefined;
        this.answerRecorder = new MediaRecorder(audioStream, options);
        this.answerRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
                this.answerChunks.push(event.data);
            }
        };
        this.answerRecorder.start(500);
    }

    stopAnswerAudioRecording() {
        if (!this.answerRecorder) {
            return Promise.resolve(null);
        }
        const recorder = this.answerRecorder;
        return new Promise((resolve) => {
            recorder.onstop = () => {
                const blob = this.answerChunks.length
                    ? new Blob(this.answerChunks, { type: recorder.mimeType || 'audio/webm' })
                    : null;
                this.answerRecorder = null;
                this.answerChunks = [];
                resolve(blob);
            };
            if (recorder.state !== "inactive") {
                recorder.stop();
            } else {
                recorder.onstop();
            }
        });
    }

    buildAsrWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const params = new URLSearchParams({
            session_id: this.sessionId,
            language: this.language || 'zh',
            audio_device: this.selectedAudioDeviceLabel || ''
        });
        const asrPath = this.resolveAppUrl('/api/user/ws/asr');
        return `${protocol}//${window.location.host}${asrPath}?${params.toString()}`;
    }

    downsampleTo16k(buffer, inputSampleRate) {
        const outputSampleRate = 16000;
        if (inputSampleRate === outputSampleRate) {
            return buffer;
        }
        const ratio = inputSampleRate / outputSampleRate;
        const outputLength = Math.round(buffer.length / ratio);
        const output = new Float32Array(outputLength);
        let offset = 0;
        for (let i = 0; i < outputLength; i++) {
            const nextOffset = Math.round((i + 1) * ratio);
            let sum = 0;
            let count = 0;
            for (; offset < nextOffset && offset < buffer.length; offset++) {
                sum += buffer[offset];
                count++;
            }
            output[i] = count ? sum / count : 0;
        }
        return output;
    }

    floatTo16BitPCM(floatBuffer) {
        const output = new Int16Array(floatBuffer.length);
        for (let i = 0; i < floatBuffer.length; i++) {
            const sample = Math.max(-1, Math.min(1, floatBuffer[i]));
            output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        }
        return output;
    }

    async startRealtimeASR() {
        if (!this.localStream || !this.sessionId || this.isAITTSPlaying || !this.answerCaptureActive) {
            return;
        }
        this.stopRealtimeAudioNodes();
        this.ensureVolumeMonitor();
        if (this.asrWebSocket && this.asrWebSocket.readyState === WebSocket.OPEN) {
            this.asrWebSocket.close();
        }

        const ws = new WebSocket(this.buildAsrWebSocketUrl());
        ws.binaryType = 'arraybuffer';
        this.asrWebSocket = ws;
        this.asrReplyResolved = false;

        this.asrReplyPromise = new Promise((resolve, reject) => {
            ws.onmessage = (event) => {
                let data = {};
                try {
                    data = JSON.parse(event.data);
                } catch (error) {
                    return;
                }

                if (data.type === 'asr_ready') {
                    console.log('[ASR][ready]', data.session_id || this.sessionId);
                    return;
                }

                if (data.type === 'asr_partial' || data.type === 'asr_final') {
                    if (this.isAITTSPlaying || !this.answerCaptureActive) {
                        return;
                    }
                    if (data.text) {
                        this.realtimeTranscript = data.text;
                        this.currentTranscript = this.pickBetterTranscript(this.currentTranscript, this.realtimeTranscript);
                    }
                    window.dispatchEvent(new CustomEvent('candidate_asr_text', { detail: data }));
                    return;
                }

                if (data.type === 'asr_error') {
                    console.warn('[ASR][error]', data.message || data);
                    return;
                }

                if (data.type === 'reply' || data.type === 'asr_done') {
                    this.asrReplyResolved = true;
                    resolve(data);
                    return;
                }

                if (data.type === 'error') {
                    const asrError = new Error(data.message || '实时语音识别失败');
                    asrError.code = data.code || '';
                    reject(asrError);
                }
            };
            ws.onerror = () => reject(new Error('实时语音识别连接异常'));
            ws.onclose = () => {
                if (!this.asrReplyResolved) {
                    reject(new Error('实时语音识别连接已关闭'));
                }
            };
        });

        await new Promise((resolve, reject) => {
            ws.onopen = () => {
                console.log('[ASR][ws_open]', this.sessionId);
                resolve();
            };
            const originalOnError = ws.onerror;
            ws.onerror = (event) => {
                if (originalOnError) originalOnError(event);
                reject(new Error('实时语音识别连接失败'));
            };
        });

        await this.startRealtimeAudioProcessor();
        this.ensureVolumeMonitor();
    }

    async startRealtimeAudioProcessor() {
        if (this.isAITTSPlaying || !this.answerCaptureActive || this.micMuted) {
            return;
        }
        const audioTracks = this.getAudioTracksForCapture();
        if (!audioTracks.length || !this.asrWebSocket || this.asrWebSocket.readyState !== WebSocket.OPEN) {
            return;
        }

        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            throw new Error('当前浏览器不支持实时音频采集');
        }

        this.audioContext = new AudioContextClass();
        if (this.micBoostContext?.state === 'suspended') {
            this.micBoostContext.resume().catch(() => {});
        }
        const audioStream = new MediaStream(audioTracks);
        this.audioSourceNode = this.audioContext.createMediaStreamSource(audioStream);
        this.audioProcessorNode = this.audioContext.createScriptProcessor(4096, 1, 1);
        this.silentGainNode = this.audioContext.createGain();
        this.silentGainNode.gain.value = 0;

        this.audioProcessorNode.onaudioprocess = (event) => {
            if (!this.asrWebSocket || this.asrWebSocket.readyState !== WebSocket.OPEN) {
                return;
            }
            if (this.isAITTSPlaying || !this.answerCaptureActive || this.micMuted) {
                return;
            }
            const input = event.inputBuffer.getChannelData(0);
            const downsampled = this.downsampleTo16k(input, this.audioContext.sampleRate);
            const pcm = this.floatTo16BitPCM(downsampled);
            this.asrWebSocket.send(pcm.buffer);
        };

        this.audioSourceNode.connect(this.audioProcessorNode);
        this.audioProcessorNode.connect(this.silentGainNode);
        this.silentGainNode.connect(this.audioContext.destination);
    }

    stopRealtimeAudioNodes() {
        if (this.audioProcessorNode) {
            this.audioProcessorNode.disconnect();
            this.audioProcessorNode.onaudioprocess = null;
            this.audioProcessorNode = null;
        }
        if (this.audioSourceNode) {
            this.audioSourceNode.disconnect();
            this.audioSourceNode = null;
        }
        if (this.silentGainNode) {
            this.silentGainNode.disconnect();
            this.silentGainNode = null;
        }
        if (this.audioContext) {
            this.audioContext.close().catch(() => {});
            this.audioContext = null;
        }
    }

    ensureVolumeMonitor() {
        const audioTrack = this.localStream?.getAudioTracks()?.[0];
        if (!audioTrack || audioTrack.readyState !== "live") {
            return;
        }
        if (!this.volumeAnalyser || !this.volumeFrame) {
            this.startVolumeMonitor();
        }
    }

    async finishRealtimeASR() {
        this.stopRealtimeAudioNodes();
        if (!this.asrWebSocket || this.asrWebSocket.readyState !== WebSocket.OPEN) {
            throw new Error('实时语音识别连接不可用');
        }
        const fallbackText = this.getBestTranscript();
        console.log('[ASR][finish_signal]', { fallback_len: fallbackText.length });
        this.asrWebSocket.send(JSON.stringify({
            action: 'finish_answer',
            fallback_text: fallbackText
        }));
        return await this.asrReplyPromise;
    }

    // 浏览器内置机械音 (作为最终兜底)
    speak(text, is_end = false, playbackId = null) {
        const activePlaybackId = playbackId || this.beginTTSPlayback();
        if (activePlaybackId !== this.ttsPlaybackId) {
            return;
        }
        this.pauseAliyunTTSPlayer();

        const utterance = new SpeechSynthesisUtterance(text);
        const lang = window.interviewLanguage || 'zh';
        utterance.lang = lang === 'en' ? 'en-US' : 'zh-CN';
        utterance.rate = 1.1;

        window._currentUtterance = utterance;
        utterance.onboundary = () => { window.dispatchEvent(new CustomEvent('ai_speaking_syllable')); };

        const resumeUI = () => this.finishTTSPlayback(activePlaybackId, is_end);

        utterance.onend = () => { resumeUI(); };
        utterance.onerror = () => {
            resumeUI();
        };

        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
    }

    setMicMuted(isMuted) {
        this.micMuted = !!isMuted;
        [this.localStream, this.processedAudioStream].forEach((stream) => {
            (stream?.getAudioTracks?.() || []).forEach((track) => {
                if (track.readyState === "live") {
                    track.enabled = !this.micMuted;
                }
            });
        });
        if (this.onAudioLevel && this.micMuted) {
            this.onAudioLevel({ level: 0, muted: true, available: true });
        }
    }

    stopAnswerCapture({ discard = true } = {}) {
        this.answerCaptureActive = false;
        if (this.recognition) {
            try {
                this.recognition.onresult = null;
                this.recognition.onerror = null;
                this.recognition.stop();
            } catch (error) {}
            this.recognition = null;
        }
        this.stopRealtimeAudioNodes();
        if (this.asrWebSocket) {
            this.asrReplyResolved = true;
            try {
                if (this.asrWebSocket.readyState === WebSocket.OPEN || this.asrWebSocket.readyState === WebSocket.CONNECTING) {
                    this.asrWebSocket.close();
                }
            } catch (error) {}
        }
        this.asrWebSocket = null;
        this.asrReplyPromise = null;
        if (this.answerRecorder) {
            try {
                this.answerRecorder.ondataavailable = null;
                this.answerRecorder.onstop = null;
                if (this.answerRecorder.state !== "inactive") {
                    this.answerRecorder.stop();
                }
            } catch (error) {}
            this.answerRecorder = null;
        }
        if (discard) {
            this.answerChunks = [];
        }
    }

    beginTTSPlayback() {
        const playbackId = ++this.ttsPlaybackId;
        this.isAITTSPlaying = true;
        this.stopAnswerCapture({ discard: true });
        this.setMicMuted(true);
        this.pauseAliyunTTSPlayer();
        window.speechSynthesis.cancel();
        if (this.onTTSStart) this.onTTSStart();
        return playbackId;
    }

    finishTTSPlayback(playbackId, is_end = false) {
        if (playbackId !== this.ttsPlaybackId) {
            return;
        }
        this.isAITTSPlaying = false;
        if (is_end) {
            if (this.onInterviewEnd) this.onInterviewEnd();
            return;
        }
        if (this.onTTSEnd) this.onTTSEnd();
        this.sendAnswerStartedSignal();
    }

    pauseAliyunTTSPlayer() {
        const player = window._globalTtsPlayer;
        if (!player) {
            return;
        }
        try {
            player.pause();
            player.onended = null;
            player.onerror = null;
        } catch (error) {}
    }

    sendAnswerStartedSignal() {
        if (this.isAITTSPlaying || this.answerCaptureActive) {
            return;
        }
        this.stopAnswerCapture({ discard: true });
        this.answerCaptureActive = true;
        this.setMicMuted(false);
        this.currentTranscript = "";
        this.browserTranscript = "";
        this.realtimeTranscript = "";
        this.startAnswerAudioRecording();
        this.startRealtimeASR().catch((error) => {
            console.warn("⚠️ 实时 ASR 启动失败，将使用音频片段上传兜底:", error);
        });
        this.recognition = this.createSpeechRecognition();
        if (!this.recognition) {
            console.warn("⚠️ 当前浏览器不支持 SpeechRecognition，将按未作答兜底。");
            return;
        }
        try {
            this.recognition.start();
        } catch (error) {
            console.warn("⚠️ 浏览器语音识别启动失败:", error);
        }
    }

    sendFinishSignal() {
        if (this.isSubmittingAnswer || this.isAITTSPlaying || !this.answerCaptureActive) {
            return;
        }
        this.setMicMuted(true);
        this.isSubmittingAnswer = true;
        this.answerCaptureActive = false;
        if (this.recognition) {
            try {
                this.recognition.stop();
            } catch (error) {
                console.warn("⚠️ 停止浏览器语音识别失败:", error);
            }
        }
        setTimeout(async () => {
            const answerBlob = await this.stopAnswerAudioRecording();
            let fallbackText = this.getBestTranscript();
            let handledByRealtimeReply = false;
            try {
                const data = await this.finishRealtimeASR();
                if (data.recognized_text) {
                    this.realtimeTranscript = data.recognized_text;
                    fallbackText = this.pickBetterTranscript(fallbackText, data.recognized_text);
                }
                if (data.type === 'reply' && data.status === 'success') {
                    handledByRealtimeReply = true;
                    this.handleReply(data);
                }
            } catch (error) {
                console.warn("⚠️ 实时 ASR 完成失败，切换音频片段上传兜底:", error);
            }
            if (handledByRealtimeReply) {
                this.isSubmittingAnswer = false;
                this.stopAnswerCapture({ discard: true });
                this.currentTranscript = "";
                this.browserTranscript = "";
                this.realtimeTranscript = "";
                return;
            }
            await this.submitCurrentAnswer(answerBlob, fallbackText);
        }, 300);
    }

    async submitCurrentAnswer(answerBlob = null, fallbackText = "") {
        this.currentTranscript = this.pickBetterTranscript(fallbackText, this.getBestTranscript());
        const answerText = this.currentTranscript || "【候选人未作答 / No Answer】";
        try {
            const data = answerBlob && answerBlob.size
                ? await submitAnswerMediaAPI(this.sessionId, answerBlob, this.language, this.currentTranscript || '', 'webm')
                : await submitAnswerAPI(this.sessionId, answerText);
            if (data.status !== "success") {
                const submitError = new Error(data.message || "提交回答失败");
                submitError.code = data.code || '';
                throw submitError;
            }
            if (data.recognized_text) {
                this.currentTranscript = data.recognized_text;
            }
            this.handleReply(data);
        } catch (error) {
            console.error("❌ 提交回答失败:", error);
            const retryText = error.code === 'asr_empty'
                ? (this.language === 'en'
                    ? "I couldn't recognize your answer. Please speak clearly and answer again."
                    : "没有识别到你的回答，请靠近麦克风并重新回答。")
                : (this.language === 'en' ? "Sorry, network error. Please try again." : "网络异常，请稍后重试。");
            this.speak(retryText, false);
        } finally {
            this.isSubmittingAnswer = false;
            this.stopAnswerCapture({ discard: true });
            this.currentTranscript = "";
            this.browserTranscript = "";
            this.realtimeTranscript = "";
        }
    }

    handleReply(data) {
        let llmReply = { display: data.text, spoken: data.text };
        try {
            const cleanText = data.text.replace(/```json/g, '').replace(/```/g, '').trim();
            llmReply = JSON.parse(cleanText);
        } catch(e) {}

        if (this.onQuestionReceived) this.onQuestionReceived(llmReply.display);

        if (data.audio_url) {
            this.playAliyunTTS(data.audio_url, llmReply.spoken, data.is_end);
        } else {
            console.warn("⚠️ 后端未返回 audio_url，降级为浏览器内置语音");
            this.speak(llmReply.spoken, data.is_end);
        }
    }

    stop() {
        this.stopAnswerCapture({ discard: true });
        this.stopVolumeMonitor();
        this.closeBoostedAudioStream();
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
            this.localStream = null;
        }
        window.speechSynthesis.cancel();
    }

    async stopAndUpload(sessionId) {
        const uploadSessionId = sessionId || this.sessionId;
        if (!uploadSessionId || !this.mediaRecorder) {
            this.stop();
            return null;
        }

        const recorder = this.mediaRecorder;
        const stopped = new Promise((resolve) => {
            recorder.onstop = resolve;
        });
        if (recorder.state !== "inactive") {
            recorder.stop();
            await stopped;
        }
        this.mediaRecorder = null;

        const blob = new Blob(this.recordedChunks, { type: recorder.mimeType || 'video/webm' });
        this.stop();
        if (!blob.size) {
            return null;
        }
        return await uploadMediaAPI(uploadSessionId, blob, 'mkv');
    }

    playAliyunTTS(audioUrl, backupText, is_end = false, retry = 0) {
        const playbackId = retry === 0 ? this.beginTTSPlayback() : this.ttsPlaybackId;
        if (playbackId !== this.ttsPlaybackId) {
            return;
        }
        console.log(`🔊 准备播放阿里云 TTS 音频 (第${retry + 1}次尝试):`, audioUrl);

        if (!window._globalTtsPlayer) {
            window._globalTtsPlayer = new Audio();
        }
        const ttsPlayer = window._globalTtsPlayer;
        let settled = false;
        const failPlayback = (error) => {
            if (settled || playbackId !== this.ttsPlaybackId) {
                return;
            }
            settled = true;
            if (retry < 2) {
                console.warn("⚠️ 音频拉取存在时差或404，500ms后自动重试...");
                setTimeout(() => {
                    if (playbackId === this.ttsPlaybackId) {
                        this.playAliyunTTS(audioUrl, backupText, is_end, retry + 1);
                    }
                }, 500);
                return;
            }
            console.error("❌ 阿里云音频加载彻底失败！已启动浏览器机器音兜底！", error);
            this.speak(backupText, is_end, playbackId);
        };

        this.pauseAliyunTTSPlayer();
        ttsPlayer.src = this.resolveAppUrl(audioUrl) + "?t=" + new Date().getTime();
        ttsPlayer.load();

        ttsPlayer.onended = () => {
            if (settled || playbackId !== this.ttsPlaybackId) {
                return;
            }
            settled = true;
            console.log("✅ 阿里云 TTS 真实人声播放完毕");
            this.finishTTSPlayback(playbackId, is_end);
        };

        ttsPlayer.onerror = failPlayback;

        const playPromise = ttsPlayer.play();
        if (playPromise !== undefined) {
            playPromise.catch(failPlayback);
        }
    }
}
