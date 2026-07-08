import { loginAPI, registerAPI, sendEmailCodeAPI, resetPasswordAPI, startInterviewAPI, cancelInterviewAPI, endInterviewAPI, getInterviewStatusAPI, faceStatusAPI, facePrecheckAPI, faceProctoringAPI } from './api.js?v=face001';
import { UI } from './ui.js?v=20260531connectionBtnA';
import { InterviewMediaManager } from './interview_media.js?v=20260530media';
import { getAuthModeConfig, getEmailCodePurpose } from './auth_state.js?v=20260528authcompact';
import { initAuthMotion } from './auth_motion.js?v=20260531memoryA';
import { initDeepSeaVoiceprint } from './auth_deepsea_voiceprint.js?v=20260530auroraCurtainA';
import { initAuthWave } from './auth_wave_canvas.js?v=20260531memoryA';
import { initRoomMotion } from './room_motion.js?v=20260530roompolish';
import { captureTemporaryCameraFrame, captureVideoFrame, createProctoringLoop } from './face_capture.js?v=face001';
import { applyI18n, createLanguageSwitcher, getLanguage, t } from './i18n.js?v=20260609i18nF';

const originalStart = UI.startAnswerSession;
UI.startAnswerSession = function() {
    originalStart.call(UI);
    const controls = document.getElementById('answerControls');
    if(controls) controls.style.display = "flex";
};

const ROOM_COPY = {
    zh: {
        connection: '\u8fde\u63a5\u826f\u597d',
        connectionRefresh: '\u5237\u65b0\u8fde\u63a5\u72b6\u6001',
        connectionChecking: '\u68c0\u6d4b\u4e2d',
        connectionReady: '\u8fde\u63a5\u826f\u597d',
        connectionWaiting: '\u7b49\u5f85\u8fde\u63a5',
        connectionDevice: '\u8bbe\u5907\u5df2\u8fde\u63a5',
        connectionOffline: '\u7f51\u7edc\u79bb\u7ebf',
        connectionIssue: '\u8fde\u63a5\u9700\u68c0\u67e5',
        reselect: '\u91cd\u9009\u8bed\u8a00',
        logout: '\u9000\u51fa\u7cfb\u7edf',
        aiTitle: 'AI \u9762\u8bd5\u5b98',
        aiAlt: 'AI \u9762\u8bd5\u5b98 Luna',
        aiStatus: '\u7cfb\u7edf\u5728\u7ebf',
        currentQuestion: '\u5f53\u524d\u95ee\u9898',
        defaultQuestion: '\u8bf7\u4ecb\u7ecd\u4f60\u7684\u5b66\u4e60\u80cc\u666f\u4e0e\u7533\u8bf7\u52a8\u673a',
        candidateView: '\u8003\u751f\u753b\u9762',
        startCamera: '\u5f00\u59cb\u9762\u8bd5',
        micLabel: '\u9ea6\u514b\u98ce\u9009\u62e9',
        micPlaceholder: '\u70b9\u51fb\u5f00\u59cb\u540e\u68c0\u6d4b',
        volume: '\u97f3\u91cf\u68c0\u6d4b',
        timer: '\u56de\u7b54\u8ba1\u65f6',
        extend: '\u5ef6\u65f6',
        finish: '\u56de\u7b54\u5b8c\u6bd5',
        dimensionsTitle: '\u8bc4\u4f30\u7ef4\u5ea6\uff08\u51715\u9879\uff09',
        dimensions: [
            ['\u5b66\u672f\u80fd\u529b', '\u8bc4\u4f30\u4f60\u7684\u5b66\u672f\u80cc\u666f\u3001\u4e13\u4e1a\u77e5\u8bc6\u53ca\u5b66\u4e60\u6f5c\u529b'],
            ['\u7814\u7a76\u6f5c\u529b', '\u8bc4\u4f30\u4f60\u7684\u7814\u7a76\u5174\u8da3\u3001\u601d\u7ef4\u6df1\u5ea6\u53ca\u521b\u65b0\u80fd\u529b'],
            ['\u6c9f\u901a\u8868\u8fbe', '\u8bc4\u4f30\u4f60\u7684\u8bed\u8a00\u7ec4\u7ec7\u3001\u8868\u8fbe\u80fd\u529b\u53ca\u903b\u8f91\u601d\u7ef4'],
            ['\u7efc\u5408\u7d20\u8d28', '\u8bc4\u4f30\u4f60\u7684\u5b66\u4e60\u6001\u5ea6\u3001\u793e\u4f1a\u8d23\u4efb\u53ca\u56e2\u961f\u534f\u4f5c'],
            ['\u7533\u8bf7\u52a8\u673a', '\u8bc4\u4f30\u4f60\u7684\u9879\u76ee\u8ba4\u77e5\u3001\u804c\u4e1a\u89c4\u5212\u53ca\u5339\u914d\u5ea6']
        ],
        noticeTitle: '\u9762\u8bd5\u987b\u77e5',
        notices: [
            '\u9762\u8bd5\u5168\u7a0b\u5c06\u8fdb\u884c\u97f3\u89c6\u9891\u5f55\u5236\uff0c\u7528\u4e8e\u7efc\u5408\u8bc4\u4f30\u3002',
            '\u8bf7\u5728\u5b89\u9759\u3001\u5149\u7ebf\u5145\u8db3\u7684\u73af\u5883\u4e2d\u8fdb\u884c\u9762\u8bd5\u3002',
            '\u8bf7\u52ff\u79bb\u5f00\u5ea7\u4f4d\u6216\u5173\u95ed\u6444\u50cf\u5934\u3001\u9ea6\u514b\u98ce\u3002',
            '\u8bf7\u52ff\u4f7f\u7528\u5916\u90e8\u8bbe\u5907\u6216\u5411\u4ed6\u4eba\u6c42\u52a9\u3002',
            '\u5982\u9047\u7f51\u7edc\u95ee\u9898\uff0c\u8bf7\u4fdd\u6301\u51b7\u9759\u5e76\u5c1d\u8bd5\u6062\u590d\u8fde\u63a5\u3002'
        ],
        trust: ['\u516c\u5e73\u516c\u6b63', '\u5b89\u5168\u53ef\u9760', '\u9690\u79c1\u4fdd\u62a4']
    },
    en: {
        connection: 'Connection good',
        connectionRefresh: 'Refresh connection status',
        connectionChecking: 'Checking',
        connectionReady: 'Connection good',
        connectionWaiting: 'Waiting to connect',
        connectionDevice: 'Device connected',
        connectionOffline: 'Network offline',
        connectionIssue: 'Check connection',
        reselect: 'Change language',
        logout: 'Log out',
        aiTitle: 'AI Interviewer',
        aiAlt: 'AI interviewer Luna',
        aiStatus: 'System online',
        currentQuestion: 'Current question',
        defaultQuestion: 'Please introduce your academic background and application motivation.',
        candidateView: 'Candidate view',
        startCamera: 'Start Interview',
        micLabel: 'Microphone',
        micPlaceholder: 'Detected after start',
        volume: 'Volume check',
        timer: 'Answer timer',
        extend: 'Extend',
        finish: 'Done',
        dimensionsTitle: 'Assessment dimensions (5 items)',
        dimensions: [
            ['Academic ability', 'Academic background, subject knowledge, and learning potential'],
            ['Research potential', 'Research interests, depth of thinking, and innovation ability'],
            ['Communication', 'Language organization, expression, and logical thinking'],
            ['Overall quality', 'Learning attitude, social responsibility, and teamwork'],
            ['Motivation', 'Program understanding, career planning, and fit']
        ],
        noticeTitle: 'Interview notice',
        notices: [
            'The interview will be recorded for comprehensive evaluation.',
            'Please interview in a quiet, well-lit environment.',
            'Do not leave your seat or turn off the camera or microphone.',
            'Do not use external devices or ask others for help.',
            'If network issues occur, stay calm and try to reconnect.'
        ],
        trust: ['Fair process', 'Secure and reliable', 'Privacy protected']
    }
};

function getRoomCopy() {
    const lang = activeRoomLanguage || getLanguage();
    return ROOM_COPY[lang];
}

const CONNECTION_COPY_KEYS = {
    ready: 'connectionReady',
    checking: 'connectionChecking',
    waiting: 'connectionWaiting',
    device: 'connectionDevice',
    offline: 'connectionOffline',
    error: 'connectionIssue'
};

let currentConnectionState = 'ready';
let currentConnectionText = '';
let activeRoomLanguage = '';

function getConnectionButton() {
    return document.getElementById('connectionStatusBtn') || document.querySelector('.connection-pill');
}

function syncConnectionButton() {
    const copy = getRoomCopy();
    const button = getConnectionButton();
    const status = document.getElementById('status');
    const copyKey = CONNECTION_COPY_KEYS[currentConnectionState] || 'connection';
    const text = currentConnectionText || copy[copyKey] || copy.connection;

    if (status) {
        status.textContent = text;
        status.removeAttribute('style');
    }

    if (button) {
        button.dataset.connectionState = currentConnectionState;
        button.setAttribute('aria-label', `${copy.connectionRefresh}: ${text}`);
        button.title = copy.connectionRefresh;
    }
}

function setConnectionButtonState(state = 'ready', text = '') {
    currentConnectionState = CONNECTION_COPY_KEYS[state] ? state : 'ready';
    currentConnectionText = text || '';
    syncConnectionButton();
}

function inferConnectionState(text = '') {
    const value = String(text).toLowerCase();
    if (!navigator.onLine || /offline|\u79bb\u7ebf|\u7f51\u7edc\u5f02\u5e38|network error/.test(value)) return 'offline';
    if (/failed|failure|error|\u5931\u8d25|\u5f02\u5e38|\u9700\u68c0\u67e5/.test(value)) return 'error';
    if (/checking|processing|uploading|submitting|speaking|evaluating|\u68c0\u6d4b|\u5904\u7406|\u4e0a\u4f20|\u6b63\u5728|\u8bc4\u4f30|\u8bb2\u8bdd/.test(value)) return 'checking';
    if (/waiting|\u7b49\u5f85|\u5f85/.test(value)) return 'waiting';
    return 'ready';
}

window.updateInterviewConnectionStatus = ({ text = '' } = {}) => {
    setConnectionButtonState(inferConnectionState(text), text);
};

async function refreshConnectionButtonStatus() {
    const button = getConnectionButton();
    if (button?.disabled) return;

    if (button) button.disabled = true;
    setConnectionButtonState('checking');

    try {
        let nextState = 'ready';
        if (!navigator.onLine) {
            nextState = 'offline';
        } else if (pendingSessionId) {
            try {
                const data = await getInterviewStatusAPI(pendingSessionId);
                nextState = data?.status === 'error' ? 'error' : 'ready';
            } catch (error) {
                console.warn('[ROOM][connection_check_failed]', error);
                nextState = 'error';
            }
        } else if (mediaManager.localStream?.getTracks().some((track) => track.readyState === 'live')) {
            nextState = 'device';
        }
        setConnectionButtonState(nextState);
    } finally {
        if (button) button.disabled = false;
    }
}

window.addEventListener('offline', () => {
    setConnectionButtonState('offline');
});

window.addEventListener('online', () => {
    setConnectionButtonState('ready');
});

function replaceElementTextAfterIcon(element, text) {
    if (!element) return;
    const icon = element.querySelector('img');
    element.textContent = '';
    if (icon) element.appendChild(icon);
    element.appendChild(document.createTextNode(text));
}

function applyInterviewRoomLanguage() {
    const room = document.getElementById('interviewSection');
    if (!room?.classList.contains('room-reference')) return;

    const copy = getRoomCopy();
    syncConnectionButton();

    const reselect = document.getElementById('reselectLangBtn');
    if (reselect) reselect.innerHTML = `<span>${copy.reselect}</span>`;

    const logout = document.getElementById('logoutBtn');
    if (logout) logout.innerHTML = `<span>${copy.logout}</span>`;

    const leftTitle = room.querySelector('.left-panel .panel-header span');
    if (leftTitle) leftTitle.textContent = copy.aiTitle;

    const avatar = document.getElementById('aiAvatarBox')?.querySelector('img');
    if (avatar) avatar.alt = copy.aiAlt;

    const aiStatusText = room.querySelector('.ai-status .room-ai-status-text') || room.querySelector('.ai-status span:last-child');
    if (aiStatusText) aiStatusText.textContent = copy.aiStatus;

    const bubbleTitle = room.querySelector('.bubble-header b');
    if (bubbleTitle) bubbleTitle.textContent = copy.currentQuestion;

    const question = document.getElementById('aiFirstQuestion');
    if (question?.dataset.roomDefaultQuestion === 'true') {
        question.textContent = copy.defaultQuestion;
    }

    const centerTitle = room.querySelector('.room-section-title b');
    if (centerTitle) centerTitle.textContent = copy.candidateView;

    const startText = document.getElementById('startBtn')?.querySelector('span');
    if (startText) startText.textContent = copy.startCamera;

    const micLabel = room.querySelector('.mic-device-box label');
    if (micLabel) micLabel.textContent = copy.micLabel;

    const micSelect = document.getElementById('micDeviceSelect');
    if (micSelect?.disabled && micSelect.options.length === 1 && !micSelect.options[0].value) {
        micSelect.options[0].textContent = copy.micPlaceholder;
    }

    const volumeLabel = room.querySelector('.volume-meter span');
    if (volumeLabel) volumeLabel.textContent = copy.volume;

    replaceElementTextAfterIcon(room.querySelector('.answer-timer-card span'), copy.timer);

    const extend = document.getElementById('extendTimeBtn');
    if (extend && !extend.textContent.includes('(')) extend.textContent = copy.extend;

    const finish = document.getElementById('finishAnswerBtn');
    if (finish) finish.textContent = copy.finish;

    const dimensionsTitle = room.querySelector('.right-panel .panel-header span');
    if (dimensionsTitle) dimensionsTitle.textContent = copy.dimensionsTitle;

    room.querySelectorAll('.dimension-card').forEach((card, index) => {
        const dimension = copy.dimensions[index];
        if (!dimension) return;
        const title = card.querySelector('h4');
        const desc = card.querySelector('p');
        if (title) title.textContent = dimension[0];
        if (desc) desc.textContent = dimension[1];
    });

    replaceElementTextAfterIcon(room.querySelector('.interview-notice h4'), copy.noticeTitle);

    room.querySelectorAll('.interview-notice li').forEach((item, index) => {
        if (copy.notices[index]) item.textContent = copy.notices[index];
    });

    room.querySelectorAll('.room-trust-row span').forEach((item, index) => {
        if (copy.trust[index]) item.textContent = copy.trust[index];
    });
}

function hydrateInterviewRoomReference() {
    const room = document.getElementById('interviewSection');
    if (!room || room.dataset.referenceHydrated === 'true') return;
    room.dataset.referenceHydrated = 'true';
    room.classList.add('room-reference');

    const asset = (name) => `/static/user/assets/${name}`;
    const status = document.getElementById('status');
    const reselect = document.getElementById('reselectLangBtn');
    const logout = document.getElementById('logoutBtn');

    const topbar = document.createElement('div');
    topbar.className = 'interview-topbar';
    topbar.innerHTML = `
        <div class="interview-brand">
            <span class="interview-logo-mark">Ai</span>
            <strong>AI面试系统</strong>
        </div>
        <div class="interview-top-status">
            <button type="button" id="connectionStatusBtn" class="connection-pill"><i aria-hidden="true"></i></button>
        </div>
        <div class="interview-top-actions"></div>
    `;
    room.prepend(topbar);

    const connection = topbar.querySelector('.connection-pill');
    if (status && connection) {
        status.className = 'system-status';
        status.setAttribute('aria-live', 'polite');
        status.textContent = '连接良好';
        connection.appendChild(status);
        const bars = document.createElement('span');
        bars.className = 'signal-bars';
        bars.setAttribute('aria-hidden', 'true');
        bars.innerHTML = '<i></i><i></i><i></i>';
        connection.appendChild(bars);
        syncConnectionButton();
        connection.addEventListener('click', () => {
            refreshConnectionButtonStatus();
        });
    }

    const topActions = topbar.querySelector('.interview-top-actions');
    if (reselect && topActions) {
        reselect.className = `${reselect.className || ''} room-action-button`;
        reselect.innerHTML = `<span>重选语言</span>`;
        topActions.appendChild(reselect);
    }
    if (logout && topActions) {
        logout.className = `${logout.className || ''} room-action-button room-logout-button`;
        logout.innerHTML = '<span>退出系统</span>';
        topActions.appendChild(logout);
    }

    const leftPanel = room.querySelector('.left-panel');
    const centerPanel = room.querySelector('.center-panel');
    const rightPanel = room.querySelector('.right-panel');

    const leftHeader = leftPanel?.querySelector('.panel-header');
    if (leftHeader) {
        leftHeader.innerHTML = '<span>AI 面试官</span><b>Luna</b>';
    }

    const avatarBox = document.getElementById('aiAvatarBox');
    if (avatarBox) {
        avatarBox.removeAttribute('style');
        avatarBox.innerHTML = `<img class="ai-avatar-img" src="${asset('interview-ai-luna.png')}" alt="AI 面试官 Luna">`;
    }

    const speakingBadge = document.getElementById('aiSpeakingBadge');
    if (speakingBadge) {
        speakingBadge.innerHTML = '';
    }

    const aiName = leftPanel?.querySelector('.ai-name');
    if (aiName) aiName.textContent = 'Luna';
    const aiStatus = leftPanel?.querySelector('.ai-status');
    if (aiStatus) {
        aiStatus.innerHTML = `<span class="status-dot"></span><span class="room-ai-status-text">系统在线</span>`;
    }
    const bubbleHeader = leftPanel?.querySelector('.bubble-header');
    if (bubbleHeader) bubbleHeader.innerHTML = '<span></span><b>当前问题</b>';
    const question = document.getElementById('aiFirstQuestion');
    if (question) {
        question.dataset.roomDefaultQuestion = 'true';
        question.textContent = '请介绍你的学习背景与申请动机';
    }

    const centerHeader = centerPanel?.querySelector('.panel-header');
    if (centerHeader) {
        centerHeader.innerHTML = `
            <span class="room-section-title"><i></i><b>考生画面</b></span>
        `;
    }
    const start = document.getElementById('startBtn');
    if (start) {
        start.innerHTML = `<img src="${asset('room-icon-camera.png')}" alt="" aria-hidden="true"><span>开启摄像头并连接 AI</span>`;
    }

    const micBox = document.getElementById('micDeviceBox');
    const micSelect = document.getElementById('micDeviceSelect');
    const micHint = document.getElementById('micDeviceHint');
    if (micBox && micSelect) {
        micBox.innerHTML = `
            <label for="micDeviceSelect">麦克风选择</label>
            <div class="mic-select-shell">
                <img src="${asset('room-icon-mic.png')}" alt="" aria-hidden="true">
            </div>
            <div class="volume-meter">
                <small class="volume-status">\u7b49\u5f85\u9ea6\u514b\u98ce\u8fde\u63a5 / Waiting for microphone</small>
                <span>音量检测</span>
                <div class="volume-bars" aria-hidden="true">
                    ${Array.from({ length: 30 }, (_, index) => `<i class="bar-${index + 1}"></i>`).join('')}
                </div>
            </div>
        `;
        micBox.querySelector('.mic-select-shell')?.appendChild(micSelect);
        if (micHint) micBox.appendChild(micHint);
    }

    const answerControls = document.getElementById('answerControls');
    const timer = document.getElementById('timerDisplay');
    const extend = document.getElementById('extendTimeBtn');
    const finish = document.getElementById('finishAnswerBtn');
    if (answerControls && timer && extend && finish) {
        answerControls.innerHTML = '<div class="answer-timer-card"><span><img src="/static/user/assets/room-icon-clock.png" alt="" aria-hidden="true">回答计时</span></div>';
        answerControls.querySelector('.answer-timer-card')?.appendChild(timer);
        extend.textContent = '延时';
        finish.textContent = '回答完毕';
        answerControls.appendChild(extend);
        answerControls.appendChild(finish);
    }

    if (rightPanel) {
        rightPanel.innerHTML = `
            <div class="panel-header"><span>评估维度（共5项）</span></div>
            <div class="dimension-card-list">
                <article class="dimension-card dim-blue"><span class="dimension-index">1</span><img src="${asset('room-icon-academic.png')}" alt="" aria-hidden="true"><div><h4>学术能力</h4><p>评估你的学术背景、专业知识及学习潜力</p></div><strong>--</strong></article>
                <article class="dimension-card dim-green"><span class="dimension-index">2</span><img src="${asset('room-icon-research.png')}" alt="" aria-hidden="true"><div><h4>研究潜力</h4><p>评估你的研究兴趣、思维深度及创新能力</p></div><strong>--</strong></article>
                <article class="dimension-card dim-orange"><span class="dimension-index">3</span><img src="${asset('room-icon-communication.png')}" alt="" aria-hidden="true"><div><h4>沟通表达</h4><p>评估你的语言组织、表达能力及逻辑思维</p></div><strong>--</strong></article>
                <article class="dimension-card dim-purple"><span class="dimension-index">4</span><img src="${asset('room-icon-quality.png')}" alt="" aria-hidden="true"><div><h4>综合素质</h4><p>评估你的学习态度、社会责任及团队协作</p></div><strong>--</strong></article>
                <article class="dimension-card dim-blue"><span class="dimension-index">5</span><img src="${asset('room-icon-motivation.png')}" alt="" aria-hidden="true"><div><h4>申请动机</h4><p>评估你的项目认知、职业规划及匹配度</p></div><strong>--</strong></article>
            </div>
            <section class="interview-notice">
                <h4><img src="${asset('prep-icon-agreement-doc.png')}" alt="" aria-hidden="true">面试须知</h4>
                <ul>
                    <li>面试全程将进行音视频录制，用于综合评估。</li>
                    <li>请在安静、光线充足的环境中进行面试。</li>
                    <li>请勿离开座位或关闭摄像头、麦克风。</li>
                    <li>请勿使用外部设备或向他人求助。</li>
                    <li>如遇网络问题，请保持冷静并尝试恢复连接。</li>
                </ul>
            </section>
            <div class="room-trust-row"><img src="${asset('room-icon-check.png')}" alt="" aria-hidden="true"><span>公平公正</span><i></i><span>安全可靠</span><i></i><span>隐私保护</span></div>
        `;
    }

    applyInterviewRoomLanguage();
}

hydrateInterviewRoomReference();
initRoomMotion('#interviewSection');

const interviewLang = document.getElementById('interviewLang');
const prepLanguageOptions = document.querySelectorAll('.prep-language-option');
const INTERVIEW_LANGUAGE_STORAGE_KEY = 'ai_interviewer_interview_language';

function normalizeInterviewLanguage(language) {
    const value = String(language || '').toLowerCase();
    return value.startsWith('en') ? 'en' : 'zh';
}

function getStoredInterviewLanguage() {
    return normalizeInterviewLanguage(localStorage.getItem(INTERVIEW_LANGUAGE_STORAGE_KEY) || getLanguage());
}

function setInterviewLanguage(language, { persist = true } = {}) {
    const nextLanguage = normalizeInterviewLanguage(language);
    if (interviewLang) {
        interviewLang.value = nextLanguage;
    }
    window.interviewLanguage = nextLanguage;
    syncPrepLanguageOptions(nextLanguage);
    if (persist) {
        localStorage.setItem(INTERVIEW_LANGUAGE_STORAGE_KEY, nextLanguage);
    }
    return nextLanguage;
}

function syncPrepLanguageOptions(value) {
    prepLanguageOptions.forEach((option) => {
        const selected = option.dataset.langValue === value;
        option.classList.toggle('is-selected', selected);
        option.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
}

if (interviewLang) {
    setInterviewLanguage(getStoredInterviewLanguage(), { persist: false });
    interviewLang.addEventListener('change', (e) => {
        setInterviewLanguage(e.target.value);
    });
}

prepLanguageOptions.forEach((option) => {
    option.addEventListener('click', () => {
        if (!interviewLang) return;
        interviewLang.value = option.dataset.langValue || 'zh';
        interviewLang.dispatchEvent(new Event('change', { bubbles: true }));
    });
});

function getLangText(zhText, enText) {
    const lang = getLanguage();
    if (lang !== 'zh') return enText;
    return String(zhText).replace(/\s*\/\s*(Pending|Ready|Uploaded|Verified|Checking|Uploading|Failed|Unsupported|No recording|Not available|Image required)\b/g, '');
}

const loginOverlay = document.getElementById('loginOverlay');
const startSection = document.getElementById('startSection');
const interviewSection = document.getElementById('interviewSection');
const emailInput = document.getElementById('emailInput');
const codeInput = document.getElementById('codeInput');
const usernameInput = document.getElementById('usernameInput');
const passwordInput = document.getElementById('passwordInput');
const sendCodeBtn = document.getElementById('sendCodeBtn');
const authStatus = document.getElementById('authStatus');
const authBtn = document.getElementById('authBtn');
const authForm = document.getElementById('authForm');
const toggleModeBtn = document.getElementById('toggleModeBtn');
const forgotPwdBtn = document.getElementById('forgotPwdBtn');
const passwordToggle = document.getElementById('passwordToggle');
const codeHelp = document.getElementById('codeHelp');
const codeHelpEmail = document.getElementById('codeHelpEmail');
const wrapCode = document.getElementById('wrapCode');
const wrapUsername = document.getElementById('wrapUsername');
const forgotPwdLinkWrap = document.getElementById('forgotPwdLinkWrap');
const brandModes = document.querySelectorAll('.brand-mode');
const prepLogoutBtn = document.getElementById('prepLogoutBtn');
const logoutBtn = document.getElementById('logoutBtn');
const reselectLangBtn = document.getElementById('reselectLangBtn');
const initInterviewBtn = document.getElementById('initInterviewBtn');
const btnStart = document.getElementById('startBtn');
const btnFinishAnswer = document.getElementById('finishAnswerBtn');
const aiSpeakingBadge = document.getElementById('aiSpeakingBadge');
const localVideo = document.getElementById('localVideo');
const statusEl = document.getElementById('status');
const aiFirstQuestionEl = document.getElementById('aiFirstQuestion');
const micDeviceSelect = document.getElementById('micDeviceSelect');
const micDeviceHint = document.getElementById('micDeviceHint');
const prepClock = document.getElementById('prepClock');

function setText(selector, key, root = document) {
    if (!root) return;
    const element = root.querySelector(selector);
    if (element) element.textContent = t(key);
}

function setPlaceholder(selector, key, root = document) {
    if (!root) return;
    const element = root.querySelector(selector);
    if (element) element.setAttribute('placeholder', t(key));
}

function replaceTextAfterIcon(selector, key, root = document) {
    if (!root) return;
    const element = root.querySelector(selector);
    if (!element) return;
    const icon = element.querySelector('img, i');
    element.textContent = '';
    if (icon) element.appendChild(icon);
    element.appendChild(document.createTextNode(t(key)));
}

function setCheckCopy(item, titleKey, descKey) {
    if (!item) return;
    const title = item.querySelector('.prep-check-copy b');
    const desc = item.querySelector('.prep-check-copy small');
    if (title) title.textContent = t(titleKey);
    if (desc) desc.textContent = t(descKey);
}

function applyStaticI18n() {
    document.title = t('brandSystem');
    applyI18n(document);

    setText('.brand-mode-login .auth-brand-title', 'brandSystem');
    setText('.brand-mode-login .auth-brand-copy', 'brandLoginCopy');
    setText('.brand-mode-register .auth-brand-title', 'brandRegisterTitle');
    setText('.brand-mode-register .auth-brand-copy', 'brandRegisterCopy');
    setText('.brand-mode-forgot .auth-brand-title', 'brandForgotTitle');
    setText('.brand-mode-forgot .auth-brand-copy', 'brandForgotCopy');
    setText('.auth-mode-hint-forgot p', 'authForgotHint');

    const registerFeatures = document.querySelectorAll('.brand-mode-register .auth-feature-item');
    setText('b', 'featureAi', registerFeatures[0]);
    setText('small', 'featureAiDesc', registerFeatures[0]);
    setText('b', 'featureFair', registerFeatures[1]);
    setText('small', 'featureFairDesc', registerFeatures[1]);
    setText('b', 'featureInclusive', registerFeatures[2]);
    setText('small', 'featureInclusiveDesc', registerFeatures[2]);

    const forgotFeatures = document.querySelectorAll('.brand-mode-forgot .auth-trust-item');
    setText('b', 'featureSecure', forgotFeatures[0]);
    setText('small', 'featureSecureDesc', forgotFeatures[0]);
    setText('b', 'featureFair', forgotFeatures[1]);
    setText('small', 'featureFairDesc', forgotFeatures[1]);
    setText('b', 'featureGrowth', forgotFeatures[2]);
    setText('small', 'featureGrowthDesc', forgotFeatures[2]);

    const accountLabelKey = currentMode === 'login' ? 'authPassport' : 'authEmail';
    const accountPlaceholderKey = currentMode === 'login' ? 'authPassportPlaceholder' : 'authEmailPlaceholder';
    setText('label[for="emailInput"]', accountLabelKey);
    setPlaceholder('#emailInput', accountPlaceholderKey);
    if (emailInput) {
        emailInput.type = currentMode === 'login' ? 'text' : 'email';
        emailInput.autocomplete = currentMode === 'login' ? 'username' : 'email';
    }
    setText('label[for="codeInput"]', 'authCode');
    setPlaceholder('#codeInput', 'authCodePlaceholder');
    setText('label[for="usernameInput"]', 'authName');
    setPlaceholder('#usernameInput', 'authNamePlaceholder');
    setText('label[for="passwordInput"]', 'authPassword');
    setText('.auth-strength-label', 'authStrength');
    setText('.auth-strength-rule', 'authStrengthRule');
    setText('.auth-remember > span:last-child', 'authRemember');
    setText('.auth-divider span', 'authOr');
    setText('#forgotPwdBtn', 'authForgotPassword');
    if (sendCodeBtn && !sendCodeBtn.disabled) sendCodeBtn.textContent = t('authGetCode');
    if (codeHelp) {
        const email = document.getElementById('codeHelpEmail')?.textContent || 'user@example.com';
        codeHelp.textContent = t('authCodeHelp', { email });
    }

    setText('.prep-brand span', 'prepBrand');
    const systemPill = document.querySelector('.prep-system-pill');
    if (systemPill) {
        const ready = systemPill.querySelector('b')?.textContent === t('prepReady');
        systemPill.innerHTML = `<i aria-hidden="true"></i>${t('prepSystem')}<b>${ready ? t('prepReady') : t('prepNormal')}</b>`;
    }
    replaceTextAfterIcon('.prep-help', 'prepHelp');
    const prepLogoutCopy = document.querySelector('#prepLogoutBtn .prep-logout-copy');
    if (prepLogoutCopy) prepLogoutCopy.textContent = t('prepLogout');
    if (prepLogoutBtn) prepLogoutBtn.setAttribute('aria-label', t('prepLogout'));
    setText('.prep-title', 'prepTitle');
    setText('.prep-copy', 'prepCopy');
    document.querySelectorAll('.prep-step b').forEach((step, index) => {
        const keys = ['prepStepDevice', 'prepStepEnvironment', 'prepStepAgreement', 'prepStepReady'];
        if (keys[index]) step.textContent = t(keys[index]);
    });
    setText('.prep-section-title', 'prepInterviewLanguage');
    document.querySelector('.prep-language-managed')?.remove();
    setText('.prep-language-help', 'prepLanguageHelp');
    document.querySelector('.prep-language-option[data-lang-value="zh"] span')?.replaceChildren(document.createTextNode(t('languageChinese')));
    document.querySelector('.prep-language-option[data-lang-value="en"] span')?.replaceChildren(document.createTextNode(t('languageEnglish')));
    const langSelectZh = document.querySelector('#interviewLang option[value="zh"]');
    const langSelectEn = document.querySelector('#interviewLang option[value="en"]');
    if (langSelectZh) langSelectZh.textContent = t('languageChinese');
    if (langSelectEn) langSelectEn.textContent = t('languageEnglish');

    const checkItems = document.querySelectorAll('.prep-check-item');
    setCheckCopy(checkItems[0], 'prepCameraTitle', 'prepCameraDesc');
    setCheckCopy(checkItems[1], 'prepMicTitle', 'prepMicDesc');
    setCheckCopy(checkItems[2], 'prepRecordingTitle', 'prepRecordingDesc');
    setCheckCopy(document.querySelector('.prep-check-item[data-check="face"]'), 'prepFaceTitle', 'prepFaceDesc');
    setText('#prepRunCheckBtn span', 'prepRunDeviceCheck');
    setText('#prepFaceVerifyBtn span', 'prepVerifyFace');
    setText('.prep-confirm-copy', 'prepAgreement');
    setText('.prep-primary-copy', 'prepEnterRoom');
    setText('.prep-footer-meta > span:first-child .prep-meta-copy', 'prepCompleteChecks');
    const clockMeta = document.querySelector('.prep-footer-meta > span:last-child .prep-meta-copy');
    if (clockMeta && prepClock) {
        clockMeta.textContent = t('prepCurrentTime');
        clockMeta.appendChild(prepClock);
    }

    if (passwordInput) {
        const key = currentMode === 'register' ? 'authSetPasswordPlaceholder' : (currentMode === 'forgot' ? 'authNewPasswordPlaceholder' : 'authPasswordPlaceholder');
        passwordInput.placeholder = t(key);
    }
    if (passwordToggle) passwordToggle.setAttribute('aria-label', passwordInput?.type === 'text' ? t('authHidePassword') : t('authShowPassword'));
}

function installLanguageSwitchers() {
    const prepActions = document.querySelector('.prep-top-actions');
    if (prepActions && !prepActions.querySelector('.language-switcher')) {
        prepActions.insertBefore(createLanguageSwitcher({ onChange: syncLanguageDrivenUI }), prepActions.querySelector('.prep-help'));
    }

    const loginOverlayEl = document.getElementById('loginOverlay');
    if (loginOverlayEl && !loginOverlayEl.querySelector('.auth-language-switcher')) {
        const switcher = createLanguageSwitcher({ onChange: syncLanguageDrivenUI });
        switcher.classList.add('auth-language-switcher');
        loginOverlayEl.appendChild(switcher);
    }
}

function syncLanguageDrivenUI() {
    updateUIState();
    applyStaticI18n();
    applyFaceVerificationLanguage();
    applyInterviewRoomLanguage();
    syncPrepLanguageOptions(window.interviewLanguage || interviewLang?.value || getStoredInterviewLanguage());
    updatePrepReadiness();
    renderVolumeMeter(latestVolumeState);
}

window.addEventListener('app-language-change', syncLanguageDrivenUI);

let pendingFirstQuestionSpoken = "";
let pendingFirstQuestionAudioUrl = ""; // 保存第一题音频地址
let pendingSessionId = "";
const mediaManager = new InterviewMediaManager();
let proctoringLoop = null;
let currentMode = 'login';
let isAITalking = false;
let processModalEl = null;
let processModalHideTimer = 0;

const PROCESS_MODAL_COPY = {
    entering: {
        titleZh: "\u6b63\u5728\u8fdb\u5165\u9762\u8bd5\u5ba4",
        titleEn: "Entering interview room",
        bodyZh: "\u6b63\u5728\u52a0\u8f7d\u9762\u8bd5\u5b98\u3001\u9898\u76ee\u548c\u9996\u9898\u8bed\u97f3\uff0c\u8bf7\u7a0d\u5019\u3002",
        bodyEn: "Loading the interviewer, question, and first-question audio. Please wait.",
        statusZh: "\u52a0\u8f7d\u4e2d",
        statusEn: "Loading"
    },
    enteringReady: {
        titleZh: "\u9762\u8bd5\u5ba4\u5df2\u51c6\u5907\u5c31\u7eea",
        titleEn: "Interview room is ready",
        bodyZh: "\u5373\u5c06\u4e3a\u60a8\u6253\u5f00\u9762\u8bd5\u5ba4\u3002",
        bodyEn: "Opening the interview room now.",
        statusZh: "\u5373\u5c06\u8fdb\u5165",
        statusEn: "Opening"
    },
    uploading: {
        titleZh: "\u6b63\u5728\u4e0a\u4f20\u9762\u8bd5\u7ed3\u679c",
        titleEn: "Uploading interview results",
        bodyZh: "\u6b63\u5728\u4e0a\u4f20\u97f3\u89c6\u9891\u548c\u9762\u8bd5\u7ed3\u679c\u4fe1\u606f\uff0c\u8bf7\u4e0d\u8981\u5173\u95ed\u9875\u9762\uff0c\u8010\u5fc3\u7b49\u5f85\u3002",
        bodyEn: "Uploading media and interview result information. Do not close this page. Please wait.",
        statusZh: "\u4e0a\u4f20\u4e2d",
        statusEn: "Uploading"
    },
    processing: {
        titleZh: "\u6b63\u5728\u751f\u6210\u9762\u8bd5\u6863\u6848",
        titleEn: "Generating interview record",
        bodyZh: "\u5f55\u5236\u5df2\u4e0a\u4f20\uff0c\u6b63\u5728\u63d0\u4ea4\u8bc4\u4ef7\u4e0e\u5f52\u6863\u4fe1\u606f\u3002\u8bf7\u7ee7\u7eed\u4fdd\u6301\u9875\u9762\u6253\u5f00\u3002",
        bodyEn: "Recording upload is complete. Submitting evaluation and archive information. Keep this page open.",
        statusZh: "\u5904\u7406\u4e2d",
        statusEn: "Processing"
    },
    complete: {
        titleZh: "\u9762\u8bd5\u7ed3\u679c\u5df2\u4fdd\u5b58",
        titleEn: "Interview results saved",
        bodyZh: "\u9762\u8bd5\u7ed3\u679c\u5df2\u4e0a\u4f20\u5e76\u5b8c\u6210\u5904\u7406\u3002",
        bodyEn: "Interview results have been uploaded and processed.",
        statusZh: "\u5b8c\u6210",
        statusEn: "Complete"
    },
    backgroundProcessing: {
        titleZh: "\u7ed3\u679c\u5df2\u63d0\u4ea4",
        titleEn: "Results submitted",
        bodyZh: "\u9762\u8bd5\u7ed3\u679c\u5df2\u63d0\u4ea4\uff0c\u540e\u53f0\u4ecd\u5728\u5904\u7406\uff0c\u60a8\u53ef\u7a0d\u540e\u5728\u7ba1\u7406\u7aef\u67e5\u770b\u3002",
        bodyEn: "Results have been submitted and are still processing in the background. Check the admin panel later.",
        statusZh: "\u540e\u53f0\u5904\u7406\u4e2d",
        statusEn: "Processing"
    },
    error: {
        titleZh: "\u64cd\u4f5c\u672a\u5b8c\u6210",
        titleEn: "Action incomplete",
        bodyZh: "\u5f53\u524d\u64cd\u4f5c\u672a\u5b8c\u6210\uff0c\u8bf7\u6839\u636e\u9875\u9762\u63d0\u793a\u91cd\u8bd5\u3002",
        bodyEn: "The current action was not completed. Follow the page message and try again.",
        statusZh: "\u8bf7\u91cd\u8bd5",
        statusEn: "Try again"
    }
};

function ensureProcessModal() {
    if (processModalEl) return processModalEl;

    processModalEl = document.createElement('div');
    processModalEl.className = 'process-modal';
    processModalEl.hidden = true;
    processModalEl.innerHTML = `
        <div class="process-modal__panel" role="alertdialog" aria-modal="true" aria-labelledby="processModalTitle" aria-describedby="processModalBody">
            <div class="process-modal__spinner" aria-hidden="true"><span></span></div>
            <div class="process-modal__copy">
                <h2 id="processModalTitle"></h2>
                <p id="processModalBody"></p>
                <div class="process-modal__status" aria-live="polite">
                    <i aria-hidden="true"></i>
                    <span id="processModalStatus"></span>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(processModalEl);
    return processModalEl;
}

function updateProcessModal(kind, override = {}) {
    const modal = ensureProcessModal();
    const copy = PROCESS_MODAL_COPY[kind] || PROCESS_MODAL_COPY.entering;
    const title = override.title || getLangText(copy.titleZh, copy.titleEn);
    const body = override.body || getLangText(copy.bodyZh, copy.bodyEn);
    const status = override.status || getLangText(copy.statusZh, copy.statusEn);

    modal.querySelector('#processModalTitle').textContent = title;
    modal.querySelector('#processModalBody').textContent = body;
    modal.querySelector('#processModalStatus').textContent = status;
    modal.dataset.state = kind;
}

function showProcessModal(kind, override = {}) {
    const modal = ensureProcessModal();
    window.clearTimeout(processModalHideTimer);
    updateProcessModal(kind, override);
    modal.hidden = false;
    document.body.classList.add('has-process-modal');
    document.body.setAttribute('aria-busy', 'true');
    window.requestAnimationFrame(() => modal.classList.add('is-visible'));
}

function hideProcessModal(delay = 0) {
    const modal = processModalEl;
    if (!modal) return;
    window.clearTimeout(processModalHideTimer);
    processModalHideTimer = window.setTimeout(() => {
        modal.classList.remove('is-visible');
        document.body.classList.remove('has-process-modal');
        document.body.removeAttribute('aria-busy');
        processModalHideTimer = window.setTimeout(() => {
            modal.hidden = true;
        }, 220);
    }, delay);
}

function updatePrepClock() {
    if (!prepClock) return;
    const now = new Date();
    const pad = (value) => String(value).padStart(2, '0');
    prepClock.textContent = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

updatePrepClock();
if (prepClock) {
    setInterval(updatePrepClock, 1000);
}

function getMicOptionLabel(device, index) {
    return device.label || getLangText(`麦克风 ${index + 1}`, `Microphone ${index + 1}`);
}

function renderMicDevices(devices = []) {
    if (!micDeviceSelect) {
        return;
    }
    micDeviceSelect.innerHTML = '';
    if (!devices.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = getLangText('未检测到麦克风', 'No microphone detected');
        micDeviceSelect.appendChild(option);
        micDeviceSelect.disabled = true;
        return;
    }

    devices.forEach((device, index) => {
        const option = document.createElement('option');
        option.value = device.deviceId;
        option.textContent = getMicOptionLabel(device, index);
        micDeviceSelect.appendChild(option);
    });
    micDeviceSelect.disabled = false;
    if (mediaManager.selectedAudioDeviceId) {
        micDeviceSelect.value = mediaManager.selectedAudioDeviceId;
    }
}

function updateMicHint(device) {
    if (!micDeviceHint) {
        return;
    }
    const label = device?.label || getLangText('默认麦克风', 'Default microphone');
    const isHeadset = mediaManager.isHeadsetLikeDevice(device);
    const isBuiltIn = mediaManager.isBuiltInMicDevice(device);
    micDeviceHint.textContent = getLangText(`当前：${label}`, `Current: ${label}`);
    micDeviceHint.style.color = isHeadset ? '#16a34a' : (isBuiltIn ? '#f97316' : '#2563eb');
    if (isBuiltIn) {
        console.warn('[AUDIO][warning] 当前输入像是电脑内置麦克风，请在下拉框选择耳机 Hands-Free。', label);
    }
}

const prepState = {
    camera: false,
    mic: false,
    recording: false,
    agreement: false,
    faceVerified: false,
    permissionChecked: false,
    checking: false,
    faceChecking: false,
    checkAttempted: false
};

function setPrepCheckState(key, state, zhText, enText) {
    const item = document.querySelector(`.prep-check-item[data-check="${key}"]`);
    if (!item) return;
    item.dataset.state = state;
    const status = item.querySelector('.prep-check-status');
    if (status) {
        status.innerHTML = `<span class="prep-status-dot" aria-hidden="true"></span>${getLangText(zhText, enText)}`;
    }
}

function setPrepStepState(index, state) {
    const step = document.querySelectorAll('.prep-step')[index];
    if (!step) return;
    step.classList.remove('is-done', 'is-active', 'is-error');
    if (state) step.classList.add(state);
    const mark = step.querySelector('.prep-step-mark');
    if (!mark) return;
    if (state === 'is-done') {
        mark.innerHTML = '<img src="/static/user/assets/prep-icon-check-circle.png" alt="" aria-hidden="true">';
    } else {
        mark.textContent = String(index + 1);
    }
}

function setPrepProgress(value) {
    const steps = document.querySelector('.prep-steps');
    if (!steps) return;
    steps.style.setProperty('--prep-progress', String(Math.max(0, Math.min(1, value))));
}

function updatePrepReadiness(message = '') {
    prepState.agreement = !!document.getElementById('prepAgreementInput')?.checked;
    const deviceCheckDone = prepState.camera && prepState.mic && prepState.permissionChecked;
    const environmentDone = prepState.recording && prepState.permissionChecked;
    const devicesReady = deviceCheckDone && environmentDone;
    const ready = devicesReady && prepState.agreement && prepState.faceVerified;

    setPrepStepState(0, deviceCheckDone ? 'is-done' : (prepState.checking || !prepState.checkAttempted ? 'is-active' : 'is-error'));
    setPrepStepState(1, environmentDone ? 'is-done' : (prepState.checking && deviceCheckDone ? 'is-active' : (prepState.checkAttempted ? 'is-error' : '')));
    setPrepStepState(2, prepState.agreement && devicesReady ? 'is-done' : (devicesReady ? 'is-active' : ''));
    setPrepStepState(3, ready ? 'is-done' : (prepState.faceChecking || (devicesReady && prepState.agreement) ? 'is-active' : ''));

    const progress = ready ? 1 : (prepState.agreement && devicesReady ? 0.82 : (devicesReady ? 0.66 : (deviceCheckDone ? 0.33 : 0)));
    setPrepProgress(progress);

    if (initInterviewBtn) {
        initInterviewBtn.disabled = !ready || prepState.checking || prepState.faceChecking;
        initInterviewBtn.classList.toggle('is-ready', ready);
    }

    const faceButton = document.getElementById('prepFaceVerifyBtn');
    if (faceButton) {
        const canVerify = devicesReady && prepState.agreement && !prepState.checking && !prepState.faceChecking;
        faceButton.disabled = !canVerify || prepState.faceVerified;
        faceButton.classList.toggle('is-done', prepState.faceVerified);
    }
    const footer = document.querySelector('.prep-meta-copy');
    if (footer) {
        footer.textContent = ready
            ? getLangText('\u5df2\u5b8c\u6210\u68c0\u6d4b\uff0c\u53ef\u8fdb\u5165\u9762\u8bd5\u5ba4', 'Checks complete. You may enter the interview room')
            : (devicesReady && prepState.agreement
                ? getLangText('\u8bf7\u5b8c\u6210\u4eba\u8138\u8eab\u4efd\u6838\u9a8c', 'Please complete face identity verification.')
                : getLangText('\u8bf7\u5b8c\u6210\u8bbe\u5907\u68c0\u6d4b\u548c\u5f55\u5236\u6388\u6743\u786e\u8ba4', 'Please complete device checks and recording authorization.'));
    }

    const initStatus = document.getElementById('initStatus');
    if (initStatus && message) {
        initStatus.textContent = message;
        initStatus.style.color = ready ? '#079b76' : '#d97706';
    }

    const systemStatus = document.querySelector('.prep-system-pill b');
    if (systemStatus) {
        systemStatus.textContent = ready
            ? getLangText('\u5c31\u7eea / Ready', 'Ready')
            : getLangText('\u5f85\u68c0\u6d4b / Pending', 'Pending');
    }

    return ready;
}

function setupPrepFunctionalChecks() {
    const privacyPanel = document.querySelector('.prep-privacy-panel');
    if (privacyPanel) privacyPanel.remove();

    const roomCard = document.querySelector('.prep-room-card');
    const checkList = document.querySelector('.prep-check-list');
    if (!roomCard || !checkList || roomCard.dataset.functionalReady === 'true') return;
    roomCard.dataset.functionalReady = 'true';
    roomCard.classList.add('prep-room-card-functional');

    if (!document.querySelector('.prep-check-item[data-check="face"]')) {
        const faceItem = document.createElement('div');
        faceItem.className = 'prep-check-item';
        faceItem.dataset.check = 'face';
        faceItem.dataset.state = 'pending';
        faceItem.innerHTML = `
            <span class="prep-check-icon"><img src="/static/user/assets/prep-icon-camera.png" alt="" aria-hidden="true"></span>
            <span class="prep-check-copy"><b>人脸身份核验<span class="i18n-en">Face Verification</span></b><small>开始面试前需核验本人和活体状态<span class="i18n-en">Verify identity and liveness before the interview.</span></small></span>
            <span class="prep-check-status"><span class="prep-status-dot" aria-hidden="true"></span>待核验 / Pending</span>
        `;
        checkList.appendChild(faceItem);
    }

    ['camera', 'mic', 'recording'].forEach((key, index) => {
        const item = checkList.children[index];
        if (item) {
            item.dataset.check = key;
            item.dataset.state = 'pending';
        }
    });

    const actions = document.createElement('div');
    actions.className = 'prep-check-actions prep-check-actions-face';
    actions.innerHTML = `
        <button type="button" id="prepRunCheckBtn" class="prep-check-action">
            <span>\u68c0\u6d4b\u8bbe\u5907 / Run device check</span>
        </button>
        <button type="button" id="prepFaceVerifyBtn" class="prep-check-action prep-face-action" disabled>
            <span>开始人脸核验 / Verify face</span>
        </button>
        <small id="prepCheckHint">\u5148\u5b8c\u6210\u8bbe\u5907\u68c0\u6d4b\u5e76\u52fe\u9009\u5f55\u5236\u6388\u6743\uff0c\u518d\u8fdb\u884c\u4eba\u8138\u6838\u9a8c\u3002 / Run device checks, confirm recording authorization, then verify your face.</small>
    `;
    checkList.after(actions);

    const agreement = document.createElement('label');
    agreement.className = 'prep-confirm-row';
    agreement.innerHTML = `
        <input id="prepAgreementInput" type="checkbox">
        <span class="prep-confirm-box" aria-hidden="true"></span>
        <span class="prep-confirm-copy">\u6211\u786e\u8ba4\u5df2\u5b8c\u6210\u8bbe\u5907\u68c0\u6d4b\uff0c\u5e76\u6388\u6743\u672c\u6b21\u9762\u8bd5\u8fdb\u884c\u97f3\u89c6\u9891\u5f55\u5236\u3002<span class="i18n-en">I confirm the device check is complete and authorize audio/video recording for this interview.</span></span>
    `;
    actions.after(agreement);

    document.getElementById('prepRunCheckBtn')?.addEventListener('click', () => {
        runPrepDeviceChecks({ requestPermission: true });
    });
    document.getElementById('prepFaceVerifyBtn')?.addEventListener('click', () => {
        runFaceVerification();
    });
    document.getElementById('prepAgreementInput')?.addEventListener('change', () => {
        const checked = !!document.getElementById('prepAgreementInput')?.checked;
        const checksPassed = prepState.camera && prepState.mic && prepState.recording && prepState.permissionChecked;
        const message = checked
            ? (checksPassed
                ? getLangText('\u5df2\u5b8c\u6210\u68c0\u6d4b\uff0c\u53ef\u8fdb\u5165\u9762\u8bd5\u5ba4\u3002', 'Checks complete. You can enter the interview room.')
                : getLangText('\u8bf7\u5148\u70b9\u51fb\u68c0\u6d4b\u8bbe\u5907\u5e76\u901a\u8fc7\u6743\u9650\u786e\u8ba4\u3002', 'Run the device check and pass permission confirmation first.'))
            : getLangText('\u8bf7\u52fe\u9009\u5f55\u5236\u6388\u6743\u786e\u8ba4\u3002', 'Please confirm recording authorization.');
        updatePrepReadiness(message);
    });
    document.querySelector('.prep-help')?.addEventListener('click', () => {
        window.location.href = '/help';
    });

    applyStaticI18n();
    setPrepCheckState('camera', 'pending', '\u5f85\u68c0\u6d4b / Pending', 'Pending');
    setPrepCheckState('mic', 'pending', '\u5f85\u68c0\u6d4b / Pending', 'Pending');
    setPrepCheckState('recording', 'pending', '\u5f85\u68c0\u6d4b / Pending', 'Pending');
    setPrepCheckState('face', prepState.faceVerified ? 'ok' : 'pending', prepState.faceVerified ? '\u5df2\u901a\u8fc7 / Verified' : '\u5f85\u6838\u9a8c / Pending', prepState.faceVerified ? 'Verified' : 'Pending');
    updatePrepReadiness();
}

const faceVerificationSteps = [
    { key: 'camera', labelKey: 'faceCameraConnected' },
    { key: 'face', labelKey: 'faceDetected' },
    { key: 'liveness', labelKey: 'faceLiveness' },
    { key: 'matching', labelKey: 'faceMatching' },
];

function applyFaceVerificationLanguage(panel = document.getElementById('faceVerificationOverlay')) {
    if (!panel) return;
    setText('#faceVerifyTitle', 'faceDialogTitle', panel);
    setText('.face-verify-head p', 'faceDialogDesc', panel);
    setText('.face-verify-status-pill b', 'faceDialogStatus', panel);
    setText('.face-verify-status-pill em', 'faceDialogStatusSub', panel);
    setText('.face-guide-frame strong', 'faceGuide', panel);
    setText('.face-verify-progress-row span', 'faceProgress', panel);
    setText('.face-verify-security p', 'facePrivacy', panel);
    faceVerificationSteps.forEach((step) => {
        const item = panel.querySelector(`.face-verify-step[data-step="${step.key}"] b`);
        if (item) item.textContent = t(step.labelKey);
    });
}

function getFaceVerificationPanel() {
    let panel = document.getElementById('faceVerificationOverlay');
    if (panel) {
        applyFaceVerificationLanguage(panel);
        return panel;
    }

    panel = document.createElement('div');
    panel.id = 'faceVerificationOverlay';
    panel.className = 'face-verification-overlay';
    panel.innerHTML = `
        <section class="face-verify-card" role="dialog" aria-modal="true" aria-labelledby="faceVerifyTitle">
            <header class="face-verify-head">
                <div>
                    <h2 id="faceVerifyTitle"></h2>
                    <p></p>
                </div>
                <span class="face-verify-status-pill"><i></i><b></b><em></em></span>
            </header>
            <div class="face-verify-video-wrap" data-state="active">
                <video id="faceVerifyVideo" autoplay muted playsinline></video>
                <div class="face-guide-frame" aria-hidden="true">
                    <span></span>
                    <strong></strong>
                </div>
                <div class="face-scan-line" aria-hidden="true"></div>
                <div class="face-result-layer" aria-live="polite"></div>
            </div>
            <div class="face-verify-live-status">
                ${faceVerificationSteps.map((step) => `
                    <div class="face-verify-step" data-step="${step.key}">
                        <span></span>
                        <b></b>
                    </div>
                `).join('')}
            </div>
            <div class="face-verify-progress-row">
                <span></span>
                <strong id="faceVerifyProgressText">0%</strong>
            </div>
            <div class="face-verify-progress"><i id="faceVerifyProgressBar"></i></div>
            <footer class="face-verify-security">
                <span>\u9501</span>
                <p></p>
            </footer>
        </section>
    `;
    document.body.appendChild(panel);
    applyFaceVerificationLanguage(panel);
    return panel;
}

function setFaceVerificationStep(panel, stepKey, state) {
    const step = panel.querySelector(`.face-verify-step[data-step="${stepKey}"]`);
    if (!step) return;
    step.dataset.state = state;
}

function setFaceVerificationProgress(panel, percent) {
    const safePercent = Math.max(0, Math.min(100, Math.round(percent)));
    const progressText = panel.querySelector('#faceVerifyProgressText');
    const progressBar = panel.querySelector('#faceVerifyProgressBar');
    if (progressText) progressText.textContent = `${safePercent}%`;
    if (progressBar) progressBar.style.width = `${safePercent}%`;
}

function showFaceVerificationResult(panel, state, title, subtitle = '') {
    const videoWrap = panel.querySelector('.face-verify-video-wrap');
    const layer = panel.querySelector('.face-result-layer');
    if (videoWrap) videoWrap.dataset.state = state;
    if (layer) {
        layer.innerHTML = `
            <div class="face-result-box">
                <span>${state === 'success' ? '\u2713' : '!'}</span>
                <strong>${title}</strong>
                ${subtitle ? `<em>${subtitle}</em>` : ''}
            </div>
        `;
    }
}

async function runFaceVerificationPanel() {
    const panel = getFaceVerificationPanel();
    const video = panel.querySelector('#faceVerifyVideo');
    const videoWrap = panel.querySelector('.face-verify-video-wrap');
    const resultLayer = panel.querySelector('.face-result-layer');
    let stream = null;

    panel.classList.add('is-visible');
    panel.querySelectorAll('.face-verify-step').forEach((step) => { step.dataset.state = 'pending'; });
    if (videoWrap) videoWrap.dataset.state = 'active';
    if (resultLayer) resultLayer.innerHTML = '';
    setFaceVerificationProgress(panel, 4);

    try {
        setFaceVerificationStep(panel, 'camera', 'active');
        stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30, max: 30 }, facingMode: 'user' },
            audio: false,
        });
        video.srcObject = stream;
        await video.play();
        await new Promise((resolve) => {
            if (video.readyState >= 2) resolve();
            else video.onloadeddata = resolve;
        });
        setFaceVerificationStep(panel, 'camera', 'done');
        setFaceVerificationProgress(panel, 24);

        setFaceVerificationStep(panel, 'face', 'active');
        await new Promise((resolve) => window.setTimeout(resolve, 650));
        setFaceVerificationStep(panel, 'face', 'done');
        setFaceVerificationProgress(panel, 44);

        setFaceVerificationStep(panel, 'liveness', 'active');
        await new Promise((resolve) => window.setTimeout(resolve, 450));
        const snapshot = await captureVideoFrame(video, { width: 720, quality: 0.82 });
        setFaceVerificationStep(panel, 'liveness', 'done');
        setFaceVerificationProgress(panel, 68);

        setFaceVerificationStep(panel, 'matching', 'active');
        const verified = await facePrecheckAPI(snapshot);
        if (verified.status !== 'success' || !verified.verified) {
            throw new Error(verified.message || getLangText('\u4eba\u8138\u8eab\u4efd\u6838\u9a8c\u672a\u901a\u8fc7', 'Face verification failed'));
        }
        setFaceVerificationStep(panel, 'matching', 'done');
        setFaceVerificationProgress(panel, 100);
        showFaceVerificationResult(panel, 'success', `\u2713 ${t('faceSuccess')}`, t('facePassed'));
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
        return verified;
    } catch (error) {
        showFaceVerificationResult(panel, 'failed', t('faceFailed'), error.message || t('faceFailed'));
        setFaceVerificationProgress(panel, 100);
        await new Promise((resolve) => window.setTimeout(resolve, 2200));
        throw error;
    } finally {
        if (stream) stream.getTracks().forEach((track) => track.stop());
        if (video) video.srcObject = null;
        panel.classList.remove('is-visible');
    }
}

async function requestTemporaryStream(constraints) {
    try {
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        stream.getTracks().forEach((track) => track.stop());
        return { ok: true };
    } catch (error) {
        return { ok: false, error };
    }
}

async function runPrepDeviceChecks({ requestPermission = false } = {}) {
    setupPrepFunctionalChecks();
    prepState.checkAttempted = true;
    prepState.faceVerified = false;
    setPrepCheckState('face', 'pending', '\u5f85\u6838\u9a8c / Pending', 'Pending');
    if (!navigator.mediaDevices?.enumerateDevices) {
        prepState.camera = false;
        prepState.mic = false;
        prepState.recording = false;
        prepState.permissionChecked = false;
        setPrepCheckState('camera', 'error', '\u6d4f\u89c8\u5668\u4e0d\u652f\u6301 / Unsupported', 'Unsupported');
        setPrepCheckState('mic', 'error', '\u6d4f\u89c8\u5668\u4e0d\u652f\u6301 / Unsupported', 'Unsupported');
        setPrepCheckState('recording', 'error', '\u65e0\u6cd5\u5f55\u5236 / No recording', 'No recording');
        updatePrepReadiness(getLangText('\u5f53\u524d\u6d4f\u89c8\u5668\u4e0d\u652f\u6301\u5a92\u4f53\u8bbe\u5907\u68c0\u6d4b\u3002', 'This browser does not support media device checks.'));
        return false;
    }

    prepState.checking = true;
    setPrepCheckState('camera', 'checking', '\u68c0\u6d4b\u4e2d / Checking', 'Checking');
    setPrepCheckState('mic', 'checking', '\u68c0\u6d4b\u4e2d / Checking', 'Checking');
    setPrepCheckState('recording', 'checking', '\u68c0\u6d4b\u4e2d / Checking', 'Checking');
    updatePrepReadiness(getLangText('\u6b63\u5728\u68c0\u6d4b\u6444\u50cf\u5934\u3001\u9ea6\u514b\u98ce\u548c\u5f55\u5236\u80fd\u529b...', 'Checking camera, microphone, and recording support...'));

    let cameraPermission = { ok: !requestPermission };
    let micPermission = { ok: !requestPermission };
    if (requestPermission) {
        cameraPermission = await requestTemporaryStream({ video: true, audio: false });
        micPermission = await requestTemporaryStream({ audio: true, video: false });
    }

    let devices = [];
    try {
        devices = await navigator.mediaDevices.enumerateDevices();
    } catch (error) {
        devices = [];
    }

    const cameras = devices.filter((device) => device.kind === 'videoinput');
    const mics = devices.filter((device) => device.kind === 'audioinput');
    const preferredMic = mediaManager.pickPreferredAudioInput(mics);
    const hasHeadset = mics.some((device) => mediaManager.isHeadsetLikeDevice(device));
    const isBuiltIn = preferredMic && mediaManager.isBuiltInMicDevice(preferredMic);
    const recorderSupported = !!window.MediaRecorder && !!navigator.mediaDevices?.getUserMedia;

    prepState.camera = cameras.length > 0 && cameraPermission.ok;
    prepState.mic = mics.length > 0 && micPermission.ok;
    prepState.recording = recorderSupported && prepState.camera && prepState.mic;
    prepState.permissionChecked = requestPermission ? (cameraPermission.ok && micPermission.ok) : prepState.permissionChecked;
    prepState.checking = false;

    setPrepCheckState(
        'camera',
        prepState.camera ? 'ok' : 'error',
        prepState.camera ? `\u6b63\u5e38\uff0c${cameras.length} \u4e2a\u8bbe\u5907` : '\u672a\u6388\u6743\u6216\u672a\u68c0\u6d4b\u5230 / Not available',
        prepState.camera ? `Normal / ${cameras.length} device(s)` : 'Not available'
    );

    const micState = prepState.mic ? (hasHeadset ? 'ok' : 'warn') : 'error';
    const micZh = prepState.mic
        ? (hasHeadset ? '\u5df2\u68c0\u6d4b\u5230\u8033\u673a\u9ea6\u514b\u98ce' : (isBuiltIn ? '\u5df2\u68c0\u6d4b\u5230\u5185\u7f6e\u9ea6\u514b\u98ce\uff0c\u5efa\u8bae\u5207\u6362\u8033\u673a' : '\u9ea6\u514b\u98ce\u53ef\u7528\uff0c\u5efa\u8bae\u4f7f\u7528\u8033\u673a'))
        : '\u672a\u6388\u6743\u6216\u672a\u68c0\u6d4b\u5230';
    const micEn = prepState.mic
        ? (hasHeadset ? 'Headset mic detected' : (isBuiltIn ? 'Built-in mic detected, headset preferred' : 'Mic available, headset preferred'))
        : 'Not available';
    setPrepCheckState('mic', micState, micZh, micEn);

    setPrepCheckState(
        'recording',
        prepState.recording ? 'ok' : 'error',
        prepState.recording ? '\u5f55\u5236\u80fd\u529b\u6b63\u5e38' : '\u5f53\u524d\u6d4f\u89c8\u5668\u4e0d\u652f\u6301\u5f55\u5236',
        prepState.recording ? 'Recording supported' : 'Recording unsupported'
    );

    const hint = document.getElementById('prepCheckHint');
    if (hint) {
        hint.textContent = prepState.camera && prepState.mic
            ? getLangText('\u8bbe\u5907\u68c0\u6d4b\u5b8c\u6210\uff0c\u8bf7\u786e\u8ba4\u5f55\u5236\u6388\u6743\u540e\u8fdb\u884c\u4eba\u8138\u6838\u9a8c\u3002', 'Device check complete. Confirm recording authorization, then verify your face.')
            : getLangText('\u8bf7\u5141\u8bb8\u6444\u50cf\u5934\u548c\u9ea6\u514b\u98ce\u6743\u9650\u540e\u91cd\u8bd5\u3002', 'Allow camera and microphone permissions, then try again.');
    }

    const checksPassed = prepState.camera && prepState.mic && prepState.recording;
    const completeMessage = checksPassed
        ? (prepState.agreement
            ? getLangText('\u68c0\u6d4b\u5b8c\u6210\uff0c\u8bf7\u7ee7\u7eed\u8fdb\u884c\u4eba\u8138\u6838\u9a8c\u3002', 'Checks complete. Continue with face verification.')
            : getLangText('\u68c0\u6d4b\u5b8c\u6210\uff0c\u8bf7\u52fe\u9009\u5f55\u5236\u6388\u6743\u786e\u8ba4\u3002', 'Checks complete. Confirm recording authorization.'))
        : getLangText('\u90e8\u5206\u8bbe\u5907\u672a\u901a\u8fc7\uff0c\u8bf7\u68c0\u67e5\u6743\u9650\u6216\u8fde\u63a5\u540e\u91cd\u8bd5\u3002', 'Some checks failed. Check permissions or device connections and retry.');

    return updatePrepReadiness(completeMessage);
}

async function ensurePrepReadyBeforeStart() {
    if (updatePrepReadiness()) return true;
    if (!prepState.permissionChecked) {
        return await runPrepDeviceChecks({ requestPermission: true });
    }
    const initStatus = document.getElementById('initStatus');
    if (initStatus) {
        initStatus.textContent = getLangText('\u8bf7\u5b8c\u6210\u8bbe\u5907\u68c0\u6d4b\u5e76\u52fe\u9009\u5f55\u5236\u6388\u6743\u786e\u8ba4\u3002', 'Please finish device checks and confirm recording authorization.');
        initStatus.style.color = '#d97706';
    }
    return false;
}

let volumeMeterFrame = null;
let latestVolumeState = { level: 0, muted: true, available: false };

function renderVolumeMeter({ level = 0, muted = false, available = true } = {}) {
    const meter = document.querySelector('.volume-meter');
    const bars = Array.from(document.querySelectorAll('.volume-bars i'));
    const status = document.querySelector('.volume-status');
    if (!meter || !bars.length) return;

    const safeLevel = Math.max(0, Math.min(1, level));
    const activeCount = muted || !available ? 0 : Math.round(safeLevel * bars.length);
    meter.classList.toggle('is-live', available && !muted && activeCount > 0);
    meter.classList.toggle('is-muted', muted || !available);
    meter.classList.toggle('is-clipping', safeLevel > 0.82);

    bars.forEach((bar, index) => {
        const active = index < activeCount;
        const scale = active ? Math.max(0.38, Math.min(1, safeLevel * 1.25 + (index % 5) * 0.035)) : 0.34;
        bar.classList.toggle('is-active', active);
        bar.style.setProperty('--bar-scale', scale.toFixed(2));
    });

    if (status) {
        status.textContent = !available
            ? getLangText('\u7b49\u5f85\u9ea6\u514b\u98ce\u8fde\u63a5', 'Waiting for microphone')
            : muted
                ? getLangText('AI \u8bb2\u8bdd\u4e2d\uff0c\u9ea6\u514b\u98ce\u5df2\u9759\u97f3', 'AI speaking, microphone muted')
                : safeLevel > 0.82
                    ? getLangText('\u97f3\u91cf\u504f\u9ad8\uff0c\u8bf7\u7565\u5fae\u964d\u4f4e\u97f3\u91cf', 'Volume high, speak slightly softer')
                    : safeLevel > 0.18
                        ? getLangText('\u58f0\u97f3\u6b63\u5e38', 'Voice level normal')
                        : getLangText('\u8bf7\u5bf9\u7740\u9ea6\u514b\u98ce\u8bd5\u8bf4\u4e00\u53e5', 'Try speaking into the microphone');
    }
}

function scheduleVolumeMeterUpdate(detail) {
    latestVolumeState = detail || latestVolumeState;
    if (volumeMeterFrame) return;
    volumeMeterFrame = window.requestAnimationFrame(() => {
        volumeMeterFrame = null;
        renderVolumeMeter(latestVolumeState);
    });
}

setupPrepFunctionalChecks();
renderVolumeMeter();

if (localStorage.getItem('ai_interviewer_token')) {
    loginOverlay.style.display = 'none';
    startSection.style.display = 'block';
    if(logoutBtn) logoutBtn.style.display = 'block';
    updatePrepReadiness();
}

function logoutUser() {
    localStorage.removeItem('ai_interviewer_token');
    location.reload();
}

if (prepLogoutBtn) {
    prepLogoutBtn.onclick = logoutUser;
}

if(logoutBtn) {
    logoutBtn.onclick = logoutUser;
}

function resetInterviewRuntimeState() {
    stopProctoringLoop();
    pendingFirstQuestionSpoken = "";
    pendingFirstQuestionAudioUrl = "";
    pendingSessionId = "";
    isAITalking = false;

    if (aiSpeakingBadge) aiSpeakingBadge.style.display = 'none';
    if (localVideo) localVideo.srcObject = null;
    if (window._globalTtsPlayer) {
        window._globalTtsPlayer.pause();
        window._globalTtsPlayer.removeAttribute('src');
        window._globalTtsPlayer.load();
    }
    window.speechSynthesis.cancel();
    window._currentUtterance = null;
}

function resetInterviewViewToSelection() {
    UI.stopAll();
    resetInterviewRuntimeState();
    activeRoomLanguage = '';

    startSection.style.display = 'block';
    interviewSection.style.display = 'none';
    updatePrepReadiness();
    document.getElementById('initStatus').innerText = "";
    document.getElementById('answerControls').style.display = 'none';
    const controls = document.querySelector('.controls-wrapper');
    if (controls) controls.style.display = 'flex';
    btnStart.style.display = 'inline-flex';
    if (aiFirstQuestionEl) {
        aiFirstQuestionEl.dataset.roomDefaultQuestion = 'true';
        aiFirstQuestionEl.innerText = getLangText("请先点击中间面板的“开启摄像头”按钮。", 'Please click the "Start Camera" button first.');
    }
    if (statusEl) {
        statusEl.innerText = `● ${getLangText("等待开始", "Waiting to start")}`;
        statusEl.style.color = "#666";
        setConnectionButtonState('waiting');
    }
}

async function returnToLanguageSelection() {
    const sessionIdToCancel = pendingSessionId;
    stopProctoringLoop();
    mediaManager.stop();
    resetInterviewViewToSelection();

    if (sessionIdToCancel) {
        try {
            await cancelInterviewAPI(sessionIdToCancel);
        } catch (error) {
            console.warn("⚠️ 取消面试会话失败:", error);
        }
    }
}

if (reselectLangBtn) {
    reselectLangBtn.onclick = async () => {
        reselectLangBtn.disabled = true;
        try {
            await returnToLanguageSelection();
        } finally {
            reselectLangBtn.disabled = false;
        }
    };
}

function updateUIState() {
    authStatus.innerText = "";
    const preservedEmail = emailInput.value;
    emailInput.value = preservedEmail;
    codeInput.value = "";
    passwordInput.value = "";
    usernameInput.value = "";

    const config = getAuthModeConfig(currentMode);
    if (loginOverlay) loginOverlay.dataset.mode = currentMode;
    brandModes.forEach((brandMode) => {
        brandMode.hidden = !brandMode.classList.contains(`brand-mode-${currentMode}`);
    });
    wrapCode.style.display = config.showCodeInput ? 'flex' : 'none';
    wrapUsername.style.display = config.showUsernameInput ? 'flex' : 'none';
    if(forgotPwdLinkWrap) forgotPwdLinkWrap.style.display = config.showForgotLink ? 'block' : 'none';
    if (codeHelp) codeHelp.style.display = 'none';

    const authTitleKey = currentMode === 'forgot' ? 'authResetTitle' : (currentMode === 'login' ? 'authLoginTitle' : 'brandRegisterTitle');
    const authSubtitleKey = currentMode === 'login' ? 'authLoginSubtitle' : (currentMode === 'register' ? 'brandRegisterCopy' : 'brandForgotCopy');
    document.querySelector('#authTitle').textContent = t(authTitleKey);
    document.querySelector('#authSubtitle').textContent = t(authSubtitleKey);
    passwordInput.placeholder = t(currentMode === 'register' ? 'authSetPasswordPlaceholder' : (currentMode === 'forgot' ? 'authNewPasswordPlaceholder' : 'authPasswordPlaceholder'));
    passwordInput.autocomplete = config.passwordAutocomplete || 'current-password';
    passwordInput.type = 'password';
    if (passwordToggle) passwordToggle.setAttribute('aria-label', '显示密码');
    document.querySelector('#authBtn').textContent = currentMode === 'forgot' ? t('authResetButton') : (currentMode === 'register' ? t('authRegisterButton') : t('authLoginButton'));
    document.querySelector('#toggleText').textContent = currentMode === 'register' ? t('authAlreadyHaveAccount') : '';
    document.querySelector('#toggleModeBtn').textContent = currentMode === 'forgot' ? t('authBackToLogin') : (currentMode === 'login' ? t('authRegisterLink') : t('authLoginButton'));
    applyStaticI18n();
    window.requestAnimationFrame(() => emailInput?.focus());
}
installLanguageSwitchers();
updateUIState();
initDeepSeaVoiceprint('#loginOverlay .auth-signal');
initAuthWave('#loginOverlay .auth-register-wave, #loginOverlay .auth-forgot-illustration');
initAuthMotion('#loginOverlay');

if (passwordToggle) {
    passwordToggle.onclick = () => {
        const shouldShow = passwordInput.type === 'password';
        passwordInput.type = shouldShow ? 'text' : 'password';
        passwordToggle.setAttribute('aria-label', shouldShow ? '隐藏密码' : '显示密码');
    };
}

toggleModeBtn.onclick = (e) => {
    e.preventDefault();
    currentMode = (currentMode === 'login') ? 'register' : 'login';
    updateUIState();
};

if (forgotPwdBtn) {
    forgotPwdBtn.onclick = (e) => {
        e.preventDefault();
        currentMode = 'forgot';
        updateUIState();
    };
}

let countdownTimer = null;
sendCodeBtn.onclick = async () => {
    const email = emailInput.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return authStatus.innerText = `⚠️ ${t('invalidEmail')}`;
    sendCodeBtn.disabled = true;
    try {
        const purpose = getEmailCodePurpose(currentMode);
        const res = await sendEmailCodeAPI(email, purpose);
        if (res.status === "success") {
            authStatus.innerText = "✅ " + res.message;
            if (codeHelp && codeHelpEmail && currentMode === 'forgot') {
                codeHelp.textContent = t('authCodeHelp', { email });
                codeHelp.style.display = 'block';
            }
            let seconds = 60;
            sendCodeBtn.innerText = `${seconds}s`;
            countdownTimer = setInterval(() => {
                seconds--;
                if (seconds <= 0) {
                    clearInterval(countdownTimer);
                    sendCodeBtn.innerText = t('authGetCode');
                    sendCodeBtn.disabled = false;
                } else sendCodeBtn.innerText = `${seconds}s`;
            }, 1000);
        } else {
            authStatus.innerText = "❌ " + res.message;
            sendCodeBtn.disabled = false;
        }
    } catch (err) {
        authStatus.innerText = `❌ ${t('networkError')}`;
        sendCodeBtn.disabled = false;
    }
};

async function handleAuthSubmit(event) {
    if (event) event.preventDefault();
    const account = emailInput.value.trim();
    const email = account;
    const pass = passwordInput.value.trim();
    const user = usernameInput.value.trim();
    const code = codeInput.value.trim();
    authBtn.disabled = true;

    try {
        if (currentMode === 'login') {
            if (!account) throw new Error(t('invalidPassport'));
            const res = await loginAPI(account, pass);
            if (res.status === "success") {
                localStorage.setItem('ai_interviewer_token', res.token);
                authStatus.innerText = `✓ ${t('loginSuccess')}`;
                setTimeout(() => {
                    loginOverlay.style.display = 'none';
                    startSection.style.display = 'block';
                    if(logoutBtn) logoutBtn.style.display = 'block';
                    updatePrepReadiness();
                }, 500);
            } else throw new Error(res.message);
        } else if (currentMode === 'register') {
            const res = await registerAPI(email, user, pass, code);
            if (res.status === "success") {
                authStatus.innerText = `✓ ${t('registerSuccess')}`;
                clearInterval(countdownTimer);
                setTimeout(() => { currentMode = 'login'; updateUIState(); }, 1500);
            } else throw new Error(res.message);
        } else if (currentMode === 'forgot') {
            const res = await resetPasswordAPI(email, pass, code);
            if (res.status === "success") {
                authStatus.innerText = `✓ ${t('passwordReset')}`;
                clearInterval(countdownTimer);
                setTimeout(() => {
                    currentMode = 'login';
                    emailInput.value = email;
                    updateUIState();
                }, 1500);
            } else throw new Error(res.message);
        }
    } catch (err) {
        authStatus.innerText = "❌ " + err.message;
    } finally {
        authBtn.disabled = false;
    }
}

if (authForm) {
    authForm.addEventListener('submit', handleAuthSubmit);
} else {
    authBtn.onclick = handleAuthSubmit;
}

async function ensureFaceReadyBeforeInterview({ force = false } = {}) {
    if (prepState.faceVerified && !force) {
        return { status: 'success', verified: true };
    }

    prepState.faceChecking = true;
    setPrepCheckState('face', 'checking', '\u6838\u9a8c\u4e2d / Checking', 'Checking');
    updatePrepReadiness(getLangText('\u6b63\u5728\u8fdb\u884c\u4eba\u8138\u8eab\u4efd\u6838\u9a8c...', 'Verifying face identity...'));

    try {
        const status = await faceStatusAPI();
        if (status.status !== 'success') {
            throw new Error(status.message || getLangText('\u4eba\u8138\u72b6\u6001\u68c0\u67e5\u5931\u8d25', 'Face status check failed'));
        }
        if (!status.enrolled || status.need_reenroll) {
            throw new Error(getLangText('\u5f53\u524d\u8d26\u53f7\u672a\u7ed1\u5b9a\u4eba\u8138\u7167\u7247\uff0c\u8bf7\u8054\u7cfb\u7ba1\u7406\u5458\u3002', 'No face photo is bound to this account. Contact the administrator.'));
        }

        const verified = await runFaceVerificationPanel();

        prepState.faceVerified = true;
        setPrepCheckState('face', 'ok', '\u5df2\u901a\u8fc7 / Verified', 'Verified');
        updatePrepReadiness(getLangText('\u4eba\u8138\u8eab\u4efd\u6838\u9a8c\u5df2\u901a\u8fc7\uff0c\u53ef\u4ee5\u8fdb\u5165\u9762\u8bd5\u5ba4\u3002', 'Face verification passed. You may enter the interview room.'));
        return verified;
    } catch (error) {
        prepState.faceVerified = false;
        setPrepCheckState('face', 'error', '\u672a\u901a\u8fc7 / Failed', 'Failed');
        updatePrepReadiness(error.message || getLangText('\u4eba\u8138\u8eab\u4efd\u6838\u9a8c\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5\u3002', 'Face verification failed. Please retry.'));
        throw error;
    } finally {
        prepState.faceChecking = false;
        updatePrepReadiness();
    }
}

async function runFaceVerification() {
    const readyForFace = prepState.camera && prepState.mic && prepState.recording && prepState.permissionChecked && prepState.agreement;
    if (!readyForFace) {
        updatePrepReadiness(getLangText('请先完成设备检测并勾选录制授权确认。', 'Complete device checks and confirm recording authorization first.'));
        return false;
    }
    try {
        await ensureFaceReadyBeforeInterview({ force: true });
        return true;
    } catch (error) {
        return false;
    }
}

function stopProctoringLoop() {
    if (proctoringLoop) {
        proctoringLoop.stop();
        proctoringLoop = null;
    }
}

function startProctoringLoop() {
    stopProctoringLoop();
    const video = document.getElementById('localVideo');
    if (!video || !pendingSessionId) return;
    proctoringLoop = createProctoringLoop({
        video,
        sessionId: pendingSessionId,
        capture: captureVideoFrame,
        upload: faceProctoringAPI,
        onResult(result) {
            if (result?.status === 'success' && result.suggestion) {
                const color = result.risk_level === 'critical' ? 'red' : 'orange';
                UI.setStatus(result.suggestion, color);
            }
        }
    });
    proctoringLoop.start();
}

initInterviewBtn.onclick = async () => {
    if (!(await ensurePrepReadyBeforeStart())) {
        return;
    }
    const lang = setInterviewLanguage(document.getElementById('interviewLang').value);
    activeRoomLanguage = lang;
    initInterviewBtn.disabled = true;
    showProcessModal('entering');
    document.getElementById('initStatus').innerText = getLangText("⏳ 正在初始化面试官...", "⏳ Initializing AI...");

    try {
        await ensureFaceReadyBeforeInterview();
        const result = await startInterviewAPI(lang);
        if (result.status === "success") {
            updateProcessModal('enteringReady');
            startSection.style.display = "none";
            interviewSection.style.display = "grid";
            applyInterviewRoomLanguage();
            setConnectionButtonState('waiting');

            let displayQ = result.first_question;
            let spokenQ = result.first_question;
            try {
                let cleanText = result.first_question.replace(/```json/g, '').replace(/```/g, '').trim();
                const parsed = JSON.parse(cleanText);
                displayQ = parsed.display || parsed.spoken;
                spokenQ = parsed.spoken;
            } catch(e) {}

            pendingFirstQuestionSpoken = spokenQ;
            pendingFirstQuestionAudioUrl = result.audio_url || "";
            pendingSessionId = result.session_id || "";
            console.log("▶️ 收到第一题音频地址:", pendingFirstQuestionAudioUrl);

            const firstQuestionEl = document.getElementById('aiFirstQuestion');
            if (firstQuestionEl) {
                firstQuestionEl.dataset.roomDefaultQuestion = 'false';
                firstQuestionEl.innerText = displayQ;
            }

            if (!live2dModel) initLive2D();
            hideProcessModal(450);
        } else throw new Error(result.message);
    } catch (err) {
        updateProcessModal('error');
        hideProcessModal(900);
        document.getElementById('initStatus').innerText = "❌ " + err.message;
        updatePrepReadiness();
    }
};

mediaManager.onQuestionReceived = (text) => {
    const questionEl = document.getElementById('aiFirstQuestion');
    if (questionEl) {
        questionEl.dataset.roomDefaultQuestion = 'false';
        questionEl.innerText = text;
    }
};

mediaManager.onAudioDevicesChanged = (devices) => {
    renderMicDevices(devices);
};

mediaManager.onAudioInputChanged = (device) => {
    if (micDeviceSelect && device?.deviceId) {
        micDeviceSelect.value = device.deviceId;
    }
    updateMicHint(device);
};

mediaManager.onAudioLevel = (detail) => {
    scheduleVolumeMeterUpdate(detail);
};

mediaManager.onTTSStart = () => {
    UI.stopAll();
    UI.setStatus(getLangText("🔇 正在讲话，您的麦克风已静音...", "🔇 Speaking, mic is muted..."), "red");
    if(aiSpeakingBadge) aiSpeakingBadge.style.display = 'block';
    isAITalking = true;
};

mediaManager.onTTSEnd = () => {
    UI.setStatus(getLangText("🟢 请开始作答", "🟢 Please start answering"), "green");
    UI.startAnswerSession();
    if(aiSpeakingBadge) aiSpeakingBadge.style.display = 'none';
    isAITalking = false;
};

mediaManager.onInterviewEnd = async () => {
    await finishAndArchiveInterview();
};

UI.onForceFinish = () => mediaManager.sendFinishSignal();
btnFinishAnswer.onclick = () => UI.forceFinish();
document.getElementById('extendTimeBtn').onclick = () => UI.extendTime();

if (micDeviceSelect) {
    micDeviceSelect.addEventListener('change', async () => {
        const deviceId = micDeviceSelect.value;
        try {
            await mediaManager.switchAudioInput(deviceId);
            const label = micDeviceSelect.options[micDeviceSelect.selectedIndex]?.textContent || '';
            UI.setStatus(getLangText(`🎙️ 已切换麦克风：${label}`, `🎙️ Microphone switched: ${label}`), "green");
        } catch (error) {
            UI.setStatus(getLangText(error.message || "麦克风切换失败", error.message || "Failed to switch microphone"), "red");
            renderMicDevices(mediaManager.audioInputDevices || []);
            updateMicHint(mediaManager.findDeviceById(mediaManager.selectedAudioDeviceId));
        }
    });
}

btnStart.onclick = async () => {
    try {
        await mediaManager.startCamera();
        await mediaManager.connect(window.interviewLanguage || 'zh', pendingSessionId);
        startProctoringLoop();
        setConnectionButtonState('ready');
        btnStart.style.display = "none";

        // ✨ 修改为优先触发阿里云音频
        if (pendingFirstQuestionAudioUrl) {
            mediaManager.playAliyunTTS(pendingFirstQuestionAudioUrl, pendingFirstQuestionSpoken, false);
        } else {
            console.warn("⚠️ 首题音频地址为空，使用浏览器内置语音");
            mediaManager.speak(pendingFirstQuestionSpoken, false);
        }
    } catch (err) {
        UI.setStatus(getLangText("连接失败: " + err.message, "Connection failed: " + err.message), "red");
        setConnectionButtonState('error');
        btnStart.style.display = "inline-flex";
    }
};

async function finishAndArchiveInterview() {
    UI.stopAll();
    stopProctoringLoop();
    const controlsGrp = document.getElementById('answerControls');
    if(controlsGrp) controlsGrp.style.display = "none";

    UI.setStatus(getLangText("🎉 面试结束！正在上传本地录制...", "🎉 Interview ended! Uploading local recording..."), "orange");
    showProcessModal('uploading');

    try {
        const uploadResult = await mediaManager.stopAndUpload(pendingSessionId);
        if (!uploadResult || uploadResult.status !== "success") {
            throw new Error(uploadResult?.message || getLangText("录制上传 OSS 失败", "Recording upload to OSS failed"));
        }
        UI.setStatus(getLangText("● 录制上传完成，后台处理中...", "● Recording uploaded. Processing in background..."), "orange");
        updateProcessModal('processing');
        const submitResult = await endInterviewAPI(pendingSessionId);
        if (submitResult.status === "error") {
            throw new Error(submitResult.message || getLangText("提交失败", "Submit failed"));
        }
        await pollInterviewProcessingStatus(pendingSessionId);
    } catch (err) {
        updateProcessModal('error');
        hideProcessModal(1600);
        UI.setStatus(getLangText("❌ " + (err.message || "网络异常"), "❌ " + (err.message || "Network Error")), "red");
    }
}

async function pollInterviewProcessingStatus(sessionId) {
    const maxAttempts = 120;
    const controls = document.querySelector('.controls-wrapper');

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        const data = await getInterviewStatusAPI(sessionId);
        const status = data.status || data.job_status;

        if (status === "success") {
            UI.setStatus(getLangText("✅ 档案处理完成！可安全关闭页面。", "✅ Records processed! You can close this page."), "green");
            updateProcessModal('complete');
            hideProcessModal(1400);
            if(controls) controls.style.display = 'none';
            return;
        }
        if (status === "partial_success") {
            UI.setStatus(
                getLangText("⚠️ 报告已保存，音视频归档待后台补偿。", "⚠️ Report saved; media archiving needs retry."),
                "orange"
            );
            updateProcessModal('backgroundProcessing');
            hideProcessModal(1600);
            if(controls) controls.style.display = 'none';
            return;
        }
        if (status === "failed") {
            throw new Error(data.message || data.error || getLangText("后台处理失败", "Background processing failed"));
        }

        const message = data.message || getLangText("后台处理中...", "Processing in background...");
        updateProcessModal('processing', { status: message });
        UI.setStatus(`● ${message}`, "orange");
        await new Promise((resolve) => setTimeout(resolve, 2000));
    }

    updateProcessModal('backgroundProcessing');
    hideProcessModal(1600);
    UI.setStatus(
        getLangText("● 档案仍在后台处理中，可稍后在管理端查看。", "● Records are still processing; check the admin panel later."),
        "orange"
    );
    if(controls) controls.style.display = 'none';
}

// ==========================================
// 数字人完美加载
// ==========================================
let live2dModel = null;
const live2dCanvas = document.getElementById('live2dCanvas');
const live2dScripts = [
    'https://fastly.jsdelivr.net/gh/dylanNew/live2d/webgl/Live2D/lib/live2d.min.js',
    'https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js',
    'https://fastly.jsdelivr.net/npm/pixi.js@6.5.2/dist/browser/pixi.min.js',
    'https://fastly.jsdelivr.net/npm/pixi-live2d-display/dist/index.min.js'
];
let live2dLoadPromise = null;

function loadScriptOnce(src) {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) return Promise.resolve();

    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        script.onload = resolve;
        script.onerror = () => reject(new Error(`Failed to load ${src}`));
        document.head.appendChild(script);
    });
}

function ensureLive2DReady() {
    if (!live2dLoadPromise) {
        live2dLoadPromise = live2dScripts.reduce(
            (chain, src) => chain.then(() => loadScriptOnce(src)),
            Promise.resolve()
        );
    }
    return live2dLoadPromise;
}

async function initLive2D() {
    if (!live2dCanvas) return;
    await ensureLive2DReady();
    const app = new PIXI.Application({
        view: live2dCanvas, transparent: true, autoStart: true, width: 400, height: 400
    });
    const modelUrl = "https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/haru/haru_greeter_t03.model3.json";
    try {
        live2dModel = await PIXI.live2d.Live2DModel.from(modelUrl);
        app.stage.addChild(live2dModel);
        live2dModel.scale.set(0.22);
        live2dModel.anchor.set(0.5, 0.5);
        live2dModel.position.set(200, 560);
        startLipSyncAnimation();
    } catch (error) {
        console.error("❌ Live2D Error:", error);
    }
}

function startLipSyncAnimation() {
    function animate() {
        requestAnimationFrame(animate);
        if (!live2dModel || !live2dModel.internalModel) return;
        let mouthY = 0;
        if (isAITalking) {
            mouthY = Math.abs(Math.sin(Date.now() / 80)) * 0.6 + Math.random() * 0.4;
        }
        try { live2dModel.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', mouthY); } catch(e) {}
    }
    animate();
}
