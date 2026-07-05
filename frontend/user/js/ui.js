export const UI = {
    timer: null,
    timeLeft: 120,
    extendCount: 0,
    onForceFinish: null,

    getLang() {
        return document.body.getAttribute('data-lang') || 'zh';
    },

    updateTimerDisplay() {
        const m = Math.floor(this.timeLeft / 60).toString().padStart(2, '0');
        const s = (this.timeLeft % 60).toString().padStart(2, '0');
        document.getElementById('timerDisplay').innerText = `${m}:${s}`;
    },

    startAnswerSession() {
        this.timeLeft = 120;
        this.extendCount = 0;
        const extendBtn = document.getElementById('extendTimeBtn');
        extendBtn.disabled = false;

        // ✨ 单语言按钮文字
        const extText = this.getLang() === 'zh' ? '延时' : 'Extend';
        extendBtn.innerText = `${extText} (${3 - this.extendCount})`;

        this.updateTimerDisplay();
        document.getElementById('answerControls').style.display = "flex";

        clearInterval(this.timer);
        this.timer = setInterval(() => {
            this.timeLeft--;
            this.updateTimerDisplay();
            if (this.timeLeft <= 0) {
                this.forceFinish();
            }
        }, 1000);
    },

    forceFinish() {
        clearInterval(this.timer);
        document.getElementById('answerControls').style.display = "none";
        const evalText = this.getLang() === 'zh' ? "已提交，评估中..." : "Submitted, evaluating...";
        this.setStatus(evalText, "orange");
        if (this.onForceFinish) this.onForceFinish();
    },

    extendTime() {
        if (this.extendCount < 3) {
            this.timeLeft += 60; // 延时 60 秒
            this.extendCount++;
            this.updateTimerDisplay();

            const extendBtn = document.getElementById('extendTimeBtn');
            const extText = this.getLang() === 'zh' ? '延时' : 'Extend';
            extendBtn.innerText = `${extText} (${3 - this.extendCount})`;

            if (this.extendCount >= 3) extendBtn.disabled = true;
        }
    },

    setStatus(text, color = "#666") {
        const statusEl = document.getElementById('status');
        statusEl.innerText = text;
        statusEl.style.color = color;
        if (window.updateInterviewConnectionStatus) {
            window.updateInterviewConnectionStatus({ text, color });
        }
    },

    stopAll() {
        clearInterval(this.timer);
        const ctrls = document.getElementById('answerControls');
        if(ctrls) ctrls.style.display = "none";
    }
};
