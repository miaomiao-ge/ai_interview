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

await import('./main.js?v=20261113sso');
