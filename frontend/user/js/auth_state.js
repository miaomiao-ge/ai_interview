const AUTH_MODE_CONFIG = {
    login: {
        showCodeInput: false,
        showUsernameInput: false,
        showForgotLink: true,
        sendCodePurpose: 'forgot',
        titleHtml: '欢迎登录 / Welcome Back',
        subtitleHtml: '请使用您的账号登录AI面试系统 / Sign in to AI面试系统',
        passwordPlaceholder: '请输入密码 / Enter your password',
        passwordAutocomplete: 'current-password',
        primaryButtonHtml: '登录 / Login',
        toggleTextHtml: '',
        toggleButtonHtml: '注册账号 / Register',
        primaryButtonText: {
            zh: '立即登录',
            en: 'Login',
        },
    },
    register: {
        showCodeInput: true,
        showUsernameInput: true,
        showForgotLink: false,
        sendCodePurpose: 'register',
        titleHtml: '',
        subtitleHtml: '',
        passwordPlaceholder: '请设置密码 / Set your password',
        passwordAutocomplete: 'new-password',
        primaryButtonHtml: '注册 / Register',
        toggleTextHtml: '已有账号？ / Already have an account?',
        toggleButtonHtml: '登录 / Login',
        primaryButtonText: {
            zh: '注册',
            en: 'Register',
        },
    },
    forgot: {
        showCodeInput: true,
        showUsernameInput: false,
        showForgotLink: false,
        sendCodePurpose: 'forgot',
        titleHtml: '重置密码 / Reset Password',
        subtitleHtml: '',
        passwordPlaceholder: '请输入新密码 / Enter a new password',
        passwordAutocomplete: 'new-password',
        primaryButtonHtml: '重置密码 / Reset Password',
        toggleTextHtml: '',
        toggleButtonHtml: '返回登录 / Back to Login',
        primaryButtonText: {
            zh: '重置密码',
            en: 'Reset Password',
        },
    },
};

export function getAuthModeConfig(mode) {
    return AUTH_MODE_CONFIG[mode] || AUTH_MODE_CONFIG.login;
}

export function getEmailCodePurpose(mode) {
    return getAuthModeConfig(mode).sendCodePurpose;
}
