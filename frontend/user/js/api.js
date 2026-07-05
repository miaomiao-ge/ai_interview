export async function sendEmailCodeAPI(email, purpose) {
    const response = await fetch('/api/user/send_email_code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, purpose })
    });
    return await response.json();
}

export async function registerAPI(email, username, password, code) {
    const response = await fetch('/api/user/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, username, password, code })
    });
    return await response.json();
}

export async function resetPasswordAPI(email, new_password, code) {
    const response = await fetch('/api/user/reset_password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, new_password, code })
    });
    return await response.json();
}

export async function loginAPI(email, password) {
    const response = await fetch('/api/user/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    return await response.json();
}

export async function startInterviewAPI(language) {
    const token = localStorage.getItem('ai_interviewer_token');
    const response = await fetch('/api/user/start_interview', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ language })
    });
    return await response.json();
}

export async function faceStatusAPI() {
    const token = localStorage.getItem('ai_interviewer_token');
    const response = await fetch('/api/face/status', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return await response.json();
}

export async function faceEnrollAPI(blob, consentVersion = '2026-06-01') {
    const token = localStorage.getItem('ai_interviewer_token');
    const form = new FormData();
    form.append('image', blob, 'face.jpg');
    form.append('consent_version', consentVersion);
    const response = await fetch('/api/face/enroll', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: form
    });
    return await response.json();
}

export async function identityDocumentUploadAPI(blob, documentType = 'passport_or_id', consentVersion = '2026-06-01') {
    const token = localStorage.getItem('ai_interviewer_token');
    const form = new FormData();
    form.append('image', blob, 'identity-document.jpg');
    form.append('document_type', documentType);
    form.append('consent_version', consentVersion);
    const response = await fetch('/api/face/identity-document', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: form
    });
    return await response.json();
}

export async function facePrecheckAPI(blob) {
    const token = localStorage.getItem('ai_interviewer_token');
    const form = new FormData();
    form.append('image', blob, 'face.jpg');
    const response = await fetch('/api/face/precheck', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: form
    });
    return await response.json();
}

export async function faceProctoringAPI(session_id, blob, capturedAt = new Date()) {
    const token = localStorage.getItem('ai_interviewer_token');
    const form = new FormData();
    form.append('session_id', session_id);
    form.append('image', blob, 'proctoring.jpg');
    form.append('client_captured_at', capturedAt.toISOString());
    const response = await fetch('/api/face/proctoring', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: form
    });
    return await response.json();
}

export async function cancelInterviewAPI(session_id) {
    const response = await fetch('/api/user/cancel_interview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id })
    });
    return await response.json();
}

export async function submitAnswerAPI(session_id, text) {
    const response = await fetch('/api/user/submit_answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id, text })
    });
    return await response.json();
}

export async function submitAnswerMediaAPI(session_id, blob, language = 'zh', fallbackText = '', ext = 'webm') {
    const params = new URLSearchParams({
        session_id,
        ext,
        language,
        fallback_text: fallbackText || ''
    });
    const response = await fetch(`/api/user/submit_answer_media?${params.toString()}`, {
        method: 'POST',
        headers: { 'Content-Type': blob.type || 'audio/webm' },
        body: blob
    });
    return await response.json();
}

export async function uploadMediaAPI(session_id, blob, ext = 'mkv') {
    const response = await fetch(`/api/user/upload_media?session_id=${encodeURIComponent(session_id)}&ext=${encodeURIComponent(ext)}`, {
        method: 'POST',
        headers: { 'Content-Type': blob.type || 'video/webm' },
        body: blob
    });
    return await response.json();
}

export async function getEvaluationAPI(session_id) {
    const token = localStorage.getItem('ai_interviewer_token');
    const response = await fetch(`/api/user/get_evaluation?session_id=${encodeURIComponent(session_id)}`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    return await response.json();
}

export async function endInterviewAPI(session_id) {
    const token = localStorage.getItem('ai_interviewer_token');
    const response = await fetch('/api/user/end_interview', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ session_id })
    });
    return await response.json();
}

export async function getInterviewStatusAPI(session_id) {
    const response = await fetch(`/api/user/interview_status?session_id=${encodeURIComponent(session_id)}`);
    return await response.json();
}
