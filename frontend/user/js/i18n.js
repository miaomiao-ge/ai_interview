const STORAGE_KEY = 'ai_interviewer_language';
const SUPPORTED_LANGUAGES = ['zh', 'en'];

const MESSAGES = {
    zh: {
        languageName: '中文',
        languageSwitcherLabel: '界面语言',
        brandSystem: 'AI面试系统',
        brandLoginCopy: '身份验证 · 语音问答 · 评价归档',
        brandRegisterTitle: '创建候选人账号',
        brandRegisterCopy: '加入AI面试系统，开启智能面试新体验',
        brandForgotTitle: '找回密码',
        brandForgotCopy: '我们将帮助你重置密码并恢复安全访问。',
        featureAi: 'AI 驱动',
        featureAiDesc: '智能评估，精准识别人才潜力',
        featureFair: '公平公正',
        featureFairDesc: '标准化流程，确保每位候选人公平对待',
        featureInclusive: '包容开放',
        featureInclusiveDesc: '多元包容，创造更多可能',
        featureSecure: '安全可靠',
        featureSecureDesc: '多重保护，确保账户安全',
        featureGrowth: '助力成长',
        featureGrowthDesc: '智能反馈，帮助你持续提升',
        authForgotHint: '请输入注册邮箱，我们将发送验证码，验证通过后即可设置新密码。',
        authEmail: '邮箱',
        authEmailPlaceholder: '请输入邮箱',
        authPassport: '护照号',
        authPassportPlaceholder: '请输入护照号',
        authCode: '验证码',
        authCodePlaceholder: '验证码',
        authGetCode: '获取',
        authCodeHelp: '验证码已发送至 {email}，请在 5 分钟内输入。',
        authName: '姓名',
        authNamePlaceholder: '真实姓名',
        authPassword: '密码',
        authPasswordPlaceholder: '请输入密码',
        authNewPasswordPlaceholder: '请输入新密码',
        authSetPasswordPlaceholder: '请设置密码',
        authShowPassword: '显示密码',
        authHidePassword: '隐藏密码',
        authStrength: '密码强度：中等',
        authStrengthRule: '8-16 位，包含字母、数字和符号',
        authRemember: '记住我',
        authOr: '或',
        authForgotPassword: '忘记密码',
        authLoginTitle: '欢迎登录',
        authLoginSubtitle: '请使用护照号登录AI面试系统',
        authLoginButton: '登录',
        authRegisterButton: '注册',
        authResetButton: '重置密码',
        authRegisterLink: '注册账号',
        authBackToLogin: '返回登录',
        authAlreadyHaveAccount: '已有账号？',
        authResetTitle: '重置密码',
        prepBrand: 'AI面试系统',
        prepSystem: '系统状态：',
        prepNormal: '正常',
        prepPending: '待检测',
        prepReady: '就绪',
        prepHelp: '帮助中心',
        prepLogout: '退出登录',
        prepTitle: '面试准备',
        prepCopy: '请完成以下准备工作，以确保面试过程顺利进行。',
        prepStepDevice: '设备检测',
        prepStepEnvironment: '环境检查',
        prepStepAgreement: '协议确认',
        prepStepReady: '准备完成',
        prepInterviewLanguage: '面试语言',
        prepLanguageHelp: '请选择你更习惯使用的面试语言，进入面试后可在设置中调整。',
        languageChinese: '中文',
        languageEnglish: '英文',
        prepCameraTitle: '摄像头可用',
        prepCameraDesc: '检测到摄像头已正常连接',
        prepMicTitle: '优先使用耳机麦克风',
        prepMicDesc: '使用耳机可获得更清晰的音频效果',
        prepRecordingTitle: '全程录音录像',
        prepRecordingDesc: '面试过程将全程录制，以确保公平公正',
        prepEnterRoom: '进入面试室',
        prepCompleteChecks: '请先完成设备检测和录制授权确认',
        prepCurrentTime: '当前时间：',
        prepFaceTitle: '人脸身份核验',
        prepFaceDesc: '开始面试前需核验本人和活体状态',
        prepRunDeviceCheck: '检测设备',
        prepVerifyFace: '开始人脸核验',
        prepCheckHint: '先完成设备检测并勾选录制授权，再进行人脸核验。',
        prepAgreement: '我确认已完成设备检测，并授权本次面试进行音视频录制。',
        statusPending: '待检测',
        statusUploaded: '已上传',
        statusVerified: '已通过',
        statusChecking: '检测中',
        statusUploading: '上传中',
        statusFailed: '失败',
        statusUnsupported: '浏览器不支持',
        statusNoRecording: '无法录制',
        statusNotAvailable: '未授权或未检测到',
        statusImageRequired: '请选择图片文件',
        faceDialogTitle: '人脸身份核验',
        faceDialogDesc: '请正视摄像头，并保持面部完整出现在取景框内。',
        faceDialogStatus: '正在采集',
        faceDialogStatusSub: '采集人脸数据',
        faceGuide: '请将面部置于框内',
        faceProgress: '人脸核验进度',
        facePrivacy: '你的人脸数据仅用于本次面试身份验证，不会用于其他用途。',
        faceCameraConnected: '摄像头连接成功',
        faceDetected: '检测到人脸',
        faceLiveness: '活体检测中',
        faceMatching: '身份信息比对中',
        faceSuccess: '人脸核验成功',
        facePassed: '人脸核验已通过',
        faceFailed: '人脸核验未通过',
        networkError: '网络异常',
        invalidEmail: '邮箱格式错误',
        invalidPassport: '请输入护照号',
        loginSuccess: '登录成功',
        registerSuccess: '注册成功',
        passwordReset: '密码已重置',
        initializingAi: '正在初始化面试官...'
    },
    en: {
        languageName: 'English',
        languageSwitcherLabel: 'Interface language',
        brandSystem: 'AI面试系统',
        brandLoginCopy: 'Identity Verification · Voice Q&A · Evaluation Archiving',
        brandRegisterTitle: 'Create Candidate Account',
        brandRegisterCopy: 'Join AI面试系统',
        brandForgotTitle: 'Recover Password',
        brandForgotCopy: 'We will help you reset your password and regain secure account access.',
        featureAi: 'AI Powered',
        featureAiDesc: 'Intelligent evaluation for candidate potential',
        featureFair: 'Fair Process',
        featureFairDesc: 'A standardized and fair process for every candidate',
        featureInclusive: 'Inclusive',
        featureInclusiveDesc: 'Diversity and inclusion create more possibilities',
        featureSecure: 'Secure',
        featureSecureDesc: 'Multi-layer protection keeps your account safe',
        featureGrowth: 'Growth',
        featureGrowthDesc: 'Smart feedback helps you improve',
        authForgotHint: 'Enter the email used during registration. We will send a verification code, then you can set a new password.',
        authEmail: 'Email',
        authEmailPlaceholder: 'Enter your email',
        authPassport: 'Passport No.',
        authPassportPlaceholder: 'Enter your passport number',
        authCode: 'Code',
        authCodePlaceholder: 'Code',
        authGetCode: 'Get',
        authCodeHelp: 'The code has been sent to {email}. Please enter it within 5 minutes.',
        authName: 'Full Name',
        authNamePlaceholder: 'Full Name',
        authPassword: 'Password',
        authPasswordPlaceholder: 'Enter your password',
        authNewPasswordPlaceholder: 'Enter a new password',
        authSetPasswordPlaceholder: 'Set your password',
        authShowPassword: 'Show password',
        authHidePassword: 'Hide password',
        authStrength: 'Password strength: Medium',
        authStrengthRule: '8-16 characters, including letters, numbers, and symbols',
        authRemember: 'Remember me',
        authOr: 'Or',
        authForgotPassword: 'Forgot Password',
        authLoginTitle: 'Welcome Back',
        authLoginSubtitle: 'Sign in with your passport number',
        authLoginButton: 'Login',
        authRegisterButton: 'Register',
        authResetButton: 'Reset Password',
        authRegisterLink: 'Register',
        authBackToLogin: 'Back to Login',
        authAlreadyHaveAccount: 'Already have an account?',
        authResetTitle: 'Reset Password',
        prepBrand: 'AI面试系统',
        prepSystem: 'System: ',
        prepNormal: 'Normal',
        prepPending: 'Pending',
        prepReady: 'Ready',
        prepHelp: 'Help Center',
        prepLogout: 'Logout',
        prepTitle: 'Interview Preparation',
        prepCopy: 'Please complete the following checks to ensure a smooth interview process.',
        prepStepDevice: 'Device Check',
        prepStepEnvironment: 'Environment Check',
        prepStepAgreement: 'Agreement',
        prepStepReady: 'Ready',
        prepInterviewLanguage: 'Interview Language',
        prepLanguageHelp: 'Choose your preferred interview language. You can adjust it in settings after entering the interview.',
        languageChinese: 'Chinese',
        languageEnglish: 'English',
        prepCameraTitle: 'Camera Available',
        prepCameraDesc: 'Camera is connected and working normally.',
        prepMicTitle: 'Headset Microphone Preferred',
        prepMicDesc: 'A headset helps capture clearer audio.',
        prepRecordingTitle: 'Full Recording',
        prepRecordingDesc: 'The interview will be recorded to ensure fairness.',
        prepEnterRoom: 'Enter Interview Room',
        prepCompleteChecks: 'Please complete device checks and recording authorization first.',
        prepCurrentTime: 'Current Time: ',
        prepFaceTitle: 'Face Verification',
        prepFaceDesc: 'Verify identity and liveness before the interview.',
        prepRunDeviceCheck: 'Run device check',
        prepVerifyFace: 'Verify face',
        prepCheckHint: 'Run device checks, confirm recording authorization, then verify your face.',
        prepAgreement: 'I confirm the device check is complete and authorize audio/video recording for this interview.',
        statusPending: 'Pending',
        statusUploaded: 'Uploaded',
        statusVerified: 'Verified',
        statusChecking: 'Checking',
        statusUploading: 'Uploading',
        statusFailed: 'Failed',
        statusUnsupported: 'Unsupported',
        statusNoRecording: 'No recording',
        statusNotAvailable: 'Not available',
        statusImageRequired: 'Image required',
        faceDialogTitle: 'Face Verification',
        faceDialogDesc: 'Please face the camera and keep your face fully inside the frame.',
        faceDialogStatus: 'Capturing',
        faceDialogStatusSub: 'Capturing Face Data',
        faceGuide: 'Keep your face inside the frame',
        faceProgress: 'Face verification progress',
        facePrivacy: 'Face data will only be used for interview identity verification.',
        faceCameraConnected: 'Camera Connected',
        faceDetected: 'Face Detected',
        faceLiveness: 'Liveness Check',
        faceMatching: 'Identity Matching',
        faceSuccess: 'Face verification successful',
        facePassed: 'Face Verification Passed',
        faceFailed: 'Face verification failed',
        networkError: 'Network Error',
        invalidEmail: 'Invalid Email',
        invalidPassport: 'Enter your passport number',
        loginSuccess: 'Login Successful',
        registerSuccess: 'Registered',
        passwordReset: 'Password reset',
        initializingAi: 'Initializing AI...'
    }
};

let currentLanguage = normalizeLanguage(localStorage.getItem(STORAGE_KEY)) || detectBrowserLanguage();

function normalizeLanguage(language) {
    const value = String(language || '').toLowerCase();
    if (value.startsWith('zh')) return 'zh';
    if (value.startsWith('en')) return 'en';
    return '';
}

function detectBrowserLanguage() {
    const browserLanguage = normalizeLanguage(navigator.language);
    if (browserLanguage) return browserLanguage;
    const preferred = Array.from(navigator.languages || []).map(normalizeLanguage).find(Boolean);
    return preferred || 'zh';
}

export function getLanguage() {
    return currentLanguage;
}

export function setLanguage(language, { persist = true } = {}) {
    const nextLanguage = normalizeLanguage(language) || 'zh';
    currentLanguage = nextLanguage;
    if (persist) localStorage.setItem(STORAGE_KEY, nextLanguage);
    document.documentElement.lang = nextLanguage === 'zh' ? 'zh-CN' : 'en';
    document.body?.setAttribute('data-lang', nextLanguage);
    window.dispatchEvent(new CustomEvent('app-language-change', { detail: { language: nextLanguage } }));
    return nextLanguage;
}

export function t(key, params = {}) {
    const template = MESSAGES[currentLanguage]?.[key] ?? MESSAGES.zh[key] ?? key;
    return Object.entries(params).reduce((text, [name, value]) => {
        return text.replaceAll(`{${name}}`, value ?? '');
    }, template);
}

export function applyI18n(root = document) {
    const scope = root || document;
    scope.querySelectorAll('[data-i18n]').forEach((element) => {
        element.textContent = t(element.dataset.i18n);
    });
    scope.querySelectorAll('[data-i18n-placeholder]').forEach((element) => {
        element.setAttribute('placeholder', t(element.dataset.i18nPlaceholder));
    });
    scope.querySelectorAll('[data-i18n-aria-label]').forEach((element) => {
        element.setAttribute('aria-label', t(element.dataset.i18nAriaLabel));
    });
    scope.querySelectorAll('[data-i18n-title]').forEach((element) => {
        element.setAttribute('title', t(element.dataset.i18nTitle));
    });
}

export function createLanguageSwitcher({ onChange } = {}) {
    const wrapper = document.createElement('div');
    wrapper.className = 'language-switcher';
    wrapper.innerHTML = `
        <label class="language-switcher__button">
            <span class="language-switcher__globe" aria-hidden="true">🌐</span>
            <span class="language-switcher__label"></span>
            <select class="language-switcher__select" aria-label="${MESSAGES.zh.languageSwitcherLabel}">
                <option value="zh">${MESSAGES.zh.languageName}</option>
                <option value="en">${MESSAGES.en.languageName}</option>
            </select>
            <span class="language-switcher__chevron" aria-hidden="true">⌄</span>
        </label>
    `;

    const select = wrapper.querySelector('.language-switcher__select');

    const applyLanguage = (language) => {
        const nextLanguage = setLanguage(language);
        render();
        onChange?.(nextLanguage);
    };

    const render = () => {
        wrapper.querySelector('.language-switcher__label').textContent = t('languageName');
        wrapper.setAttribute('aria-label', t('languageSwitcherLabel'));
        select.setAttribute('aria-label', t('languageSwitcherLabel'));
        select.value = currentLanguage;
    };

    select.addEventListener('change', () => {
        applyLanguage(select.value);
    });

    window.addEventListener('app-language-change', render);
    render();
    return wrapper;
}

setLanguage(currentLanguage, { persist: false });
