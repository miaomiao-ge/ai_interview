import { createLanguageSwitcher, getLanguage } from './i18n.js?v=20260609i18nF';

const HELP_MESSAGES = {
    zh: {
        pageTitle: '帮助中心 - AI面试系统',
        navLabel: '帮助中心导航',
        navFlow: '流程说明',
        navGuide: '使用说明',
        navFaq: '常见问题',
        navBack: '返回',
        heroTitle: '帮助中心',
        heroSubtitle: 'AI面试系统使用说明与操作指南',
        prepSummaryLabel: '面试前准备摘要',
        prepLabel: '面试前建议',
        prepTime: '10 分钟',
        prepCopy: '预留设备检测、授权确认与人脸核验时间，保持浏览器授权开启。',
        flowTitle: '系统流程说明',
        flowDeviceTitle: '设备检测',
        flowDeviceCopy: '确认摄像头、麦克风与录制能力可用，并允许浏览器访问设备。',
        flowEnvironmentTitle: '环境检查',
        flowEnvironmentCopy: '选择安静、光线稳定的位置，关闭可能干扰面试的应用通知。',
        flowFaceTitle: '人脸核验',
        flowFaceCopy: '按页面提示完成本人身份核验，确保面部完整出现在画面中。',
        flowInterviewTitle: '进入面试',
        flowInterviewCopy: '系统生成 AI 面试官语音与题目，按页面提示完成问答。',
        guideTitle: '使用说明',
        guideStartTitle: '如何开始面试',
        guideStartCopy: '登录后进入面试准备页，依次完成语言选择、设备检测、授权确认与人脸核验，按钮变为可用后即可进入面试室。',
        guideDeviceTitle: '如何通过设备检测',
        guideDeviceCopy: '点击检测设备后，在浏览器弹窗中允许摄像头和麦克风权限。若权限被拒绝，请在地址栏左侧重新开启。',
        guideCameraTitle: '摄像头/麦克风要求',
        guideCameraCopy: '建议使用清晰摄像头与耳机麦克风，保持麦克风未静音，避免多人同时出现在画面中。',
        guideNetworkTitle: '网络建议',
        guideNetworkCopy: '优先使用稳定 Wi-Fi 或有线网络，面试过程中不要切换网络、刷新页面或关闭浏览器标签页。',
        faqTitle: '常见问题',
        faqCameraQuestion: '摄像头无法打开怎么办？',
        faqCameraAnswer: '先检查浏览器权限是否允许访问摄像头，再确认摄像头未被会议软件占用。修改权限后刷新页面并重新进行设备检测。',
        faqFaceQuestion: '人脸识别失败怎么办？',
        faqFaceAnswer: '请调整到光线充足的位置，正对摄像头，摘下遮挡面部的物品，并确保面部完整出现在取景框内。',
        faqLagQuestion: '页面卡顿如何处理？',
        faqLagAnswer: '关闭其他高占用程序，保持网络稳定。若仍然卡顿，请暂停无关下载或切换到性能更好的设备。',
        faqMobileQuestion: '是否支持手机端？',
        faqMobileAnswer: '当前暂未完成移动端适配，正式面试请使用电脑完成，以获得更稳定的摄像头、麦克风和网络体验。',
        noticeTitle: '注意事项',
        noticeLight: '请保持环境光线充足，面部清晰可见。',
        noticeFace: '请勿遮挡面部，避免佩戴口罩、墨镜等影响识别的物品。',
        noticePage: '面试过程中请勿切换页面、刷新页面或关闭浏览器。'
    },
    en: {
        pageTitle: 'Help Center - AI面试系统',
        navLabel: 'Help center navigation',
        navFlow: 'Flow',
        navGuide: 'Guide',
        navFaq: 'FAQ',
        navBack: 'Back',
        heroTitle: 'Help Center',
        heroSubtitle: 'Instructions and operating guide for AI面试系统',
        prepSummaryLabel: 'Pre-interview preparation summary',
        prepLabel: 'Before the interview',
        prepTime: '10 minutes',
        prepCopy: 'Allow time for device checks, recording authorization, and face verification. Keep browser permissions enabled.',
        flowTitle: 'System Flow',
        flowDeviceTitle: 'Device Check',
        flowDeviceCopy: 'Confirm the camera, microphone, and recording capability are available, and allow browser access to your devices.',
        flowEnvironmentTitle: 'Environment Check',
        flowEnvironmentCopy: 'Choose a quiet location with stable lighting, and close app notifications that may interrupt the interview.',
        flowFaceTitle: 'Face Verification',
        flowFaceCopy: 'Follow the page prompts to complete identity verification, and keep your full face visible in the frame.',
        flowInterviewTitle: 'Enter Interview',
        flowInterviewCopy: 'The system generates the AI interviewer voice and questions. Follow the page prompts to answer.',
        guideTitle: 'Usage Guide',
        guideStartTitle: 'How to start',
        guideStartCopy: 'After signing in, go to interview preparation and complete language selection, device check, authorization confirmation, and face verification. Once the button is enabled, enter the interview room.',
        guideDeviceTitle: 'How to pass device check',
        guideDeviceCopy: 'Click device check, then allow camera and microphone permissions in the browser prompt. If permission is blocked, re-enable it from the left side of the address bar.',
        guideCameraTitle: 'Camera and microphone requirements',
        guideCameraCopy: 'Use a clear camera and headset microphone. Keep the microphone unmuted and avoid multiple people appearing in the frame.',
        guideNetworkTitle: 'Network recommendations',
        guideNetworkCopy: 'Use stable Wi-Fi or wired network when possible. Do not switch networks, refresh the page, or close the browser tab during the interview.',
        faqTitle: 'FAQ',
        faqCameraQuestion: 'What if the camera cannot open?',
        faqCameraAnswer: 'Check whether browser permission allows camera access, then confirm the camera is not being used by meeting software. After changing permissions, refresh the page and run device check again.',
        faqFaceQuestion: 'What if face recognition fails?',
        faqFaceAnswer: 'Move to a well-lit location, face the camera, remove items that block your face, and keep your full face inside the frame.',
        faqLagQuestion: 'What if the page becomes slow?',
        faqLagAnswer: 'Close other high-usage programs and keep the network stable. If it is still slow, pause unrelated downloads or switch to a better-performing device.',
        faqMobileQuestion: 'Is mobile supported?',
        faqMobileAnswer: 'Mobile adaptation is not complete yet. Please use a computer for the formal interview to get a more stable camera, microphone, and network experience.',
        noticeTitle: 'Notice',
        noticeLight: 'Keep the environment well lit and your face clearly visible.',
        noticeFace: 'Do not cover your face. Avoid masks, sunglasses, or other items that may affect recognition.',
        noticePage: 'Do not switch pages, refresh the page, or close the browser during the interview.'
    }
};

function getHelpText(key) {
    const language = getLanguage() === 'en' ? 'en' : 'zh';
    return HELP_MESSAGES[language][key] ?? HELP_MESSAGES.zh[key] ?? key;
}

function applyHelpLanguage() {
    document.title = getHelpText('pageTitle');

    document.querySelectorAll('[data-help-i18n]').forEach((element) => {
        element.textContent = getHelpText(element.dataset.helpI18n);
    });

    document.querySelectorAll('[data-help-i18n-aria-label]').forEach((element) => {
        element.setAttribute('aria-label', getHelpText(element.dataset.helpI18nAriaLabel));
    });
}

const languageSlot = document.getElementById('helpLanguageSlot');
if (languageSlot && !languageSlot.querySelector('.language-switcher')) {
    languageSlot.appendChild(createLanguageSwitcher({ onChange: applyHelpLanguage }));
}

window.addEventListener('app-language-change', applyHelpLanguage);
applyHelpLanguage();

const backButton = document.getElementById('helpBackBtn');

backButton?.addEventListener('click', () => {
    if (window.history.length > 1) {
        window.history.back();
        return;
    }

    window.location.href = '/';
});

document.querySelectorAll('.faq-list details').forEach((item) => {
    item.addEventListener('toggle', () => {
        if (!item.open) return;

        document.querySelectorAll('.faq-list details').forEach((other) => {
            if (other !== item) other.open = false;
        });
    });
});
