export function captureVideoFrame(video, { width = 720, quality = 0.82 } = {}) {
    if (!video || !video.videoWidth || !video.videoHeight) {
        return Promise.reject(new Error('Camera image is not ready'));
    }

    const ratio = video.videoHeight / video.videoWidth;
    const canvas = document.createElement('canvas');
    canvas.width = Math.min(width, video.videoWidth);
    canvas.height = Math.round(canvas.width * ratio);
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => {
            if (!blob) {
                reject(new Error('Failed to capture camera image'));
                return;
            }
            resolve(blob);
        }, 'image/jpeg', quality);
    });
}

export async function captureTemporaryCameraFrame(options = {}) {
    const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 720 }, height: { ideal: 540 }, facingMode: 'user' },
        audio: false
    });
    const video = document.createElement('video');
    video.muted = true;
    video.playsInline = true;
    video.srcObject = stream;

    try {
        await video.play();
        await new Promise((resolve) => {
            if (video.readyState >= 2) {
                resolve();
                return;
            }
            video.onloadeddata = resolve;
        });
        return await captureVideoFrame(video, options);
    } finally {
        stream.getTracks().forEach((track) => track.stop());
        video.srcObject = null;
    }
}

export function createProctoringLoop({
    video,
    sessionId,
    intervalSeconds = 10,
    capture,
    upload,
    onResult,
}) {
    let timer = null;
    let stopped = true;
    let running = false;

    const tick = async () => {
        if (stopped || running) return;
        running = true;
        try {
            const blob = await capture(video);
            const result = await upload(sessionId, blob, new Date());
            if (onResult) onResult(result);
        } catch (error) {
            console.warn('[FACE][proctoring_failed]', error);
        } finally {
            running = false;
        }
    };

    return {
        start() {
            if (timer) return;
            stopped = false;
            timer = window.setInterval(tick, Math.max(10, intervalSeconds) * 1000);
            window.setTimeout(tick, 3000);
        },
        stop() {
            stopped = true;
            if (timer) {
                window.clearInterval(timer);
                timer = null;
            }
        }
    };
}
