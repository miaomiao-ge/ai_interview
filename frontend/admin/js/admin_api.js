// 管理端登录接口
export async function adminLoginAPI(username, password) {
    const res = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    return await res.json();
}

export async function getAdminProfileAPI(token) {
    const res = await fetch('/api/admin/me', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return { httpStatus: res.status, data: await res.json() };
}

export function canSeeAdminUsersTab(role) {
    return role === 'super_admin';
}

export function normalizeAdminRow(row = {}) {
    const username = row.username || '';
    const rawDisplayName = (row.display_name || '').trim();
    const rawEmail = (row.email || '').trim();

    return {
        id: row.id ?? null,
        username,
        display_name: rawDisplayName || '-',
        email: rawEmail || '-',
        role: row.role || 'admin',
        status: row.status || 'active',
        last_login_at: row.last_login_at || '-',
        created_at: row.created_at || '-',
        created_by: row.created_by ?? null,
        raw_display_name: rawDisplayName,
        raw_email: rawEmail
    };
}

// 获取管理员数据接口 (携带 Token)
export async function getAdminRecordsAPI(token) {
    const res = await fetch('/api/admin/records', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return { httpStatus: res.status, data: await res.json() };
}

// 更新复核状态接口
export async function updateRecordReviewAPI(token, recordId, status, remark) {
    const res = await fetch(`/api/admin/records/${recordId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ status, remark })
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function deleteRecordAPI(token, recordId) {
    const res = await fetch(`/api/admin/records/${recordId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function batchDeleteRecordsAPI(token, ids) {
    const res = await fetch('/api/admin/records/batch_delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ ids })
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function retryArchiveAPI(token, recordId) {
    const res = await fetch(`/api/admin/records/${recordId}/retry_archive`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return { httpStatus: res.status, data: await res.json() };
}

// ====== ✨ 新增题库与 Prompt 接口 ======
export async function getQuestionsAPI(token) {
    return await (await fetch('/api/admin/questions', { headers: { 'Authorization': `Bearer ${token}` }})).json();
}

export async function saveQuestionAPI(token, id, category, content) {
    const method = id ? 'PUT' : 'POST';
    const url = id ? `/api/admin/questions/${id}` : '/api/admin/questions';
    return await (await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ category, content }) })).json();
}

export async function deleteQuestionAPI(token, id) {
    return await (await fetch(`/api/admin/questions/${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` }})).json();
}

export async function batchDeleteQuestionsAPI(token, ids) {
    return await (await fetch('/api/admin/questions/batch_delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ ids })
    })).json();
}

export async function getPromptsAPI(token) {
    return await (await fetch('/api/admin/prompts', { headers: { 'Authorization': `Bearer ${token}` }})).json();
}

export async function savePromptsAPI(token, base_prompt, eval_prompt) {
    return await (await fetch('/api/admin/prompts', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ base_prompt, eval_prompt }) })).json();
}

export async function getAdminUsersAPI(token) {
    const res = await fetch('/api/admin/admins', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function createAdminUserAPI(token, payload) {
    const res = await fetch('/api/admin/admins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(payload)
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function updateAdminUserAPI(token, adminId, payload) {
    const res = await fetch(`/api/admin/admins/${adminId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(payload)
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function resetAdminPasswordAPI(token, adminId, new_password) {
    const res = await fetch(`/api/admin/admins/${adminId}/reset_password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ new_password })
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function toggleAdminStatusAPI(token, adminId, status) {
    const res = await fetch(`/api/admin/admins/${adminId}/toggle_status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ status })
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function getAdminLoginRecordsAPI(token) {
    const res = await fetch('/api/admin/admins/login_records', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return { httpStatus: res.status, data: await res.json() };
}

export async function getAdminActionLogsAPI(token) {
    const res = await fetch('/api/admin/admins/action_logs', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return { httpStatus: res.status, data: await res.json() };
}
