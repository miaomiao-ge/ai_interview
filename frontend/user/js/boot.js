const params = new URLSearchParams(location.search);
const ticket = params.get('sso_ticket');

if (ticket) {
    params.delete('sso_ticket');
    const query = params.toString();
    history.replaceState({}, '', location.pathname + (query ? '?' + query : '') + location.hash);
    try {
        const response = await fetch('/api/user/sso_login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ticket}),
        });
        const result = await response.json().catch(() => ({}));
        if (result.status === 'success' && result.token) {
            localStorage.setItem('ai_interviewer_token', result.token);
            sessionStorage.removeItem('ai_sso_error');
        } else {
            localStorage.removeItem('ai_interviewer_token');
            sessionStorage.setItem('ai_sso_error', result.message || '自动登录失败，请重新登录');
        }
    } catch (error) {
        localStorage.removeItem('ai_interviewer_token');
        sessionStorage.setItem('ai_sso_error', '自动登录失败，请检查网络后重新登录');
    }
}

// 心理测评是面试准备页之前的必经步骤：已登录但未提交测评时先进入测评页。
const token = localStorage.getItem('ai_interviewer_token') || '';
let redirectingToAssessment = false;
if (token) {
    try {
        const response = await fetch('/api/user/assessment/result', {
            headers: {Authorization: `Bearer ${token}`},
            cache: 'no-store',
        });
        const data = await response.json().catch(() => ({}));
        if (data.status === 'success' && data.assessment_status !== 'submitted') {
            redirectingToAssessment = true;
            sessionStorage.setItem('assessment_return_to', location.pathname + location.search);
            location.replace('/interview/assessment/');
        }
    } catch (error) {
        console.warn('[assessment] status check failed', error);
    }
}

if (!redirectingToAssessment && !location.pathname.startsWith('/interview/assessment')) {
    await import('./main.js?v=20261120assessment');
}
document.documentElement.removeAttribute('data-sso-pending');
