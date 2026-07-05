import {
    adminLoginAPI,
    batchDeleteRecordsAPI,
    batchDeleteQuestionsAPI,
    canSeeAdminUsersTab,
    createAdminUserAPI,
    deleteRecordAPI,
    deleteQuestionAPI,
    getAdminActionLogsAPI,
    getAdminLoginRecordsAPI,
    getAdminProfileAPI,
    getAdminRecordsAPI,
    getAdminUsersAPI,
    getPromptsAPI,
    getQuestionsAPI,
    normalizeAdminRow,
    resetAdminPasswordAPI,
    savePromptsAPI,
    saveQuestionAPI,
    toggleAdminStatusAPI,
    updateAdminUserAPI,
    updateRecordReviewAPI,
} from './admin_api.js?v=20260530adminbatchrender';
import { extractTotalScore, parseInterviewReport } from './report_parser.mjs?v=20260421a';
import { getLatestRecordPerEmail } from './record_metrics.mjs?v=20260428a';
import { sortRecordsByScore } from './record_sort.mjs?v=20260702a';
import { initAuthMotion } from '/static/user/js/auth_motion.js?v=20260530polish';

const loginOverlay = document.getElementById('adminLoginOverlay');
const mainDashboard = document.getElementById('mainDashboard');
const authStatus = document.getElementById('adminAuthStatus');
const navMenu = document.getElementById('navMenu');

const recordSearchInput = document.getElementById('recordSearchInput');
const recordSearchBtn = document.getElementById('recordSearchBtn');
const recordSearchResetBtn = document.getElementById('recordSearchResetBtn');
const recordScoreSortBtn = document.getElementById('recordScoreSortBtn');
const recordsTableBody = document.getElementById('recordsTableBody');
const reportContent = document.getElementById('reportContent');
const recordsTableContainer = document.getElementById('recordsTableContainer');
const selectAllRecordsCheckbox = document.getElementById('selectAllRecords');
const batchDeleteRecordsBtn = document.getElementById('batchDeleteRecordsBtn');
const selectAllQuestionsCheckbox = document.getElementById('selectAllQuestions');
const batchDeleteQuestionsBtn = document.getElementById('batchDeleteQuestionsBtn');

const questionModal = document.getElementById('questionModal');
const qCategoryInput = document.getElementById('qCategory');
const qContentInput = document.getElementById('qContent');
const modalTitle = document.getElementById('modalTitle');
const saveQBtn = document.getElementById('saveQBtn');
const cancelQBtn = document.getElementById('cancelQBtn');
const addQuestionBtn = document.getElementById('addQuestionBtn');

const adminsTableBody = document.getElementById('adminsTableBody');
const adminLoginRecordsBody = document.getElementById('adminLoginRecordsBody');
const adminActionLogsBody = document.getElementById('adminActionLogsBody');
const refreshAdminUsersBtn = document.getElementById('refreshAdminUsersBtn');
const refreshAdminLoginRecordsBtn = document.getElementById('refreshAdminLoginRecordsBtn');
const refreshAdminActionLogsBtn = document.getElementById('refreshAdminActionLogsBtn');
const addAdminBtn = document.getElementById('addAdminBtn');

const adminUserModal = document.getElementById('adminUserModal');
const adminUserModalTitle = document.getElementById('adminUserModalTitle');
const adminUserModalHint = document.getElementById('adminUserModalHint');
const adminUserUsernameInput = document.getElementById('adminUserUsername');
const adminUserDisplayNameInput = document.getElementById('adminUserDisplayName');
const adminUserEmailInput = document.getElementById('adminUserEmail');
const adminUserRoleSelect = document.getElementById('adminUserRole');
const adminUserPasswordField = document.getElementById('adminUserPasswordField');
const adminUserPasswordInput = document.getElementById('adminUserPassword');
const cancelAdminUserBtn = document.getElementById('cancelAdminUserBtn');
const saveAdminUserBtn = document.getElementById('saveAdminUserBtn');

const resetAdminPasswordModal = document.getElementById('resetAdminPasswordModal');
const resetAdminPasswordTitle = document.getElementById('resetAdminPasswordTitle');
const resetAdminPasswordHint = document.getElementById('resetAdminPasswordHint');
const resetAdminPasswordInput = document.getElementById('resetAdminPasswordInput');
const cancelResetAdminPasswordBtn = document.getElementById('cancelResetAdminPasswordBtn');
const confirmResetAdminPasswordBtn = document.getElementById('confirmResetAdminPasswordBtn');
initAuthMotion('#adminLoginOverlay');

let recordsData = [];
let filteredRecordsData = [];
let recordScoreSortOrder = null;
let questionsData = [];
let adminUsersData = [];
let adminLoginRecordsData = [];
let adminActionLogsData = [];
let activeAdminProfile = null;
let currentSelectedRecordId = null;
let editingQuestionId = null;
let editingAdminId = null;
let resettingAdminId = null;
const selectedQuestionIds = new Set();
const selectedRecordIds = new Set();
let html2pdfLoadPromise = null;
const ADMIN_REMEMBER_ENABLED_KEY = 'admin_remember_account_enabled';
const ADMIN_REMEMBERED_ACCOUNT_KEY = 'admin_remembered_account';

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function clearAdminSession() {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_role');
    localStorage.removeItem('admin_username');
    activeAdminProfile = null;
}

function setAuthStatus(message, color = '#e74c3c') {
    authStatus.innerText = message;
    authStatus.style.color = color;
}

function isSuperAdmin() {
    return canSeeAdminUsersTab(localStorage.getItem('admin_role'));
}

function requireSuperAdmin(message = '该用户权限不足。') {
    if (isSuperAdmin()) {
        return true;
    }
    alert(message);
    return false;
}

function handleAuthFailure(httpStatus) {
    if (httpStatus !== 401 && httpStatus !== 403) {
        return false;
    }
    alert('登录已失效或无权限，请重新登录。');
    clearAdminSession();
    location.reload();
    return true;
}

function getReviewBadgeClass(status) {
    if (status === '拟录取') return 'badge-pass';
    if (status === '淘汰') return 'badge-fail';
    return 'badge-pending';
}

function getScoreBadgeClass(score) {
    if (score >= 85) return 'badge-score-high';
    if (score >= 70) return 'badge-score-mid';
    return 'badge-score-low';
}

function getScoreTier(score) {
    if (score >= 85) return 'high';
    if (score >= 70) return 'mid';
    return 'low';
}

function normalizeFaceStatus(status) {
    const value = String(status || '').toLowerCase();
    if (value === 'passed' || value === 'success' || value === 'verified') return '已通过';
    if (value === 'failed' || value === 'error' || value === 'rejected') return '未通过';
    if (value === 'disabled') return '未启用';
    return '待核验';
}

function getFaceBadgeClass(status) {
    const value = String(status || '').toLowerCase();
    if (value === 'passed' || value === 'success' || value === 'verified') return 'badge-pass';
    if (value === 'failed' || value === 'error' || value === 'rejected') return 'badge-fail';
    return 'badge-pending';
}

function normalizeRiskLevel(risk) {
    const value = String(risk || 'none').toLowerCase();
    if (value === 'critical') return '严重';
    if (value === 'high') return '高风险';
    if (value === 'medium') return '中风险';
    if (value === 'low') return '低风险';
    return '无明显风险';
}

function getRiskBadgeClass(risk) {
    const value = String(risk || 'none').toLowerCase();
    if (value === 'critical' || value === 'high') return 'badge-fail';
    if (value === 'medium' || value === 'low') return 'badge-score-mid';
    return 'badge-pass';
}

function formatFaceScore(score) {
    const numeric = Number(score);
    return Number.isFinite(numeric) ? numeric.toFixed(2) : '-';
}

function formatFlagName(flag) {
    const names = {
        no_face: '未检测到人脸',
        multiple_faces: '多张人脸',
        multiple_persons: '多人入镜',
        phone_detected: '疑似手机',
        earphone_detected: '疑似耳机',
        person_absent: '人员离席',
        head_down: '低头',
        head_turned: '转头',
        face_not_centered: '人脸偏离',
        identity_recheck_failed: '过程身份复核异常',
        identity_recheck_passed: '过程身份复核通过',
    };
    return names[flag] || flag;
}

function getPercentTier(percent) {
    if (percent >= 80) return 'high';
    if (percent >= 60) return 'mid';
    return 'low';
}

function getProcessingStatus(record) {
    const evaluateStatus = record.evaluate_status || '';
    const archiveStatus = record.archive_status || '';
    if (evaluateStatus === 'success' && archiveStatus === 'success') return '完成';
    if (evaluateStatus === 'success' && archiveStatus === 'partial_success') return '部分完成';
    if (evaluateStatus === 'success' && archiveStatus === 'error') return '待补传';
    if (evaluateStatus === 'processing') return '评估中';
    if (archiveStatus === 'processing') return '归档中';
    if (evaluateStatus === 'failed' || archiveStatus === 'failed') return '失败';
    return archiveStatus || evaluateStatus || '待处理';
}

function getProcessingBadgeClass(status) {
    if (status === '完成') return 'badge-pass';
    if (status === '部分完成' || status === '待补传' || status === '评估中' || status === '归档中') return 'badge-score-mid';
    if (status === '失败') return 'badge-fail';
    return 'badge-pending';
}

function checkPermissions() {
    const superOnlyNodes = document.querySelectorAll('.admin-super-only');
    if (isSuperAdmin()) {
        superOnlyNodes.forEach((node) => {
            node.style.removeProperty('display');
            node.style.removeProperty('visibility');
        });
        return;
    }
    superOnlyNodes.forEach((node) => node.remove());
}

function visibleRecordIds() {
    return filteredRecordsData.map((record) => record.id).filter((id) => id != null);
}

function syncRecordBatchControls() {
    const selectableIds = visibleRecordIds();
    const selectableIdSet = new Set(selectableIds);
    [...selectedRecordIds].forEach((id) => {
        if (!selectableIdSet.has(id)) {
            selectedRecordIds.delete(id);
        }
    });

    if (selectAllRecordsCheckbox) {
        selectAllRecordsCheckbox.checked = selectableIds.length > 0 && selectableIds.every((id) => selectedRecordIds.has(id));
        selectAllRecordsCheckbox.indeterminate = selectedRecordIds.size > 0 && !selectAllRecordsCheckbox.checked;
    }

    if (batchDeleteRecordsBtn) {
        const count = selectedRecordIds.size;
        batchDeleteRecordsBtn.disabled = count === 0;
        batchDeleteRecordsBtn.textContent = count ? `批量删除 (${count})` : '批量删除';
    }
}

async function restoreSession() {
    const token = localStorage.getItem('admin_token');
    if (!token) {
        return;
    }

    const profileResp = await getAdminProfileAPI(token);
    if (profileResp.httpStatus !== 200 || profileResp.data?.status !== 'success') {
        clearAdminSession();
        return;
    }

    activeAdminProfile = profileResp.data.data;
    localStorage.setItem('admin_role', activeAdminProfile.role);
    localStorage.setItem('admin_username', activeAdminProfile.username);
    checkPermissions();
    loginOverlay.style.display = 'none';
    mainDashboard.style.display = 'block';
    await fetchRecords();
}

async function loginAdmin() {
    const username = adminUsernameInput?.value.trim() || '';
    const password = adminPasswordInput?.value.trim() || '';
    if (!username || !password) {
        setAuthStatus('账号和密码不能为空！');
        return;
    }

    setAuthStatus('正在验证...', '#3498db');
    try {
        const result = await adminLoginAPI(username, password);
        if (result.status !== 'success') {
            setAuthStatus(result.message || '登录失败，请重试。');
            return;
        }

        localStorage.setItem('admin_token', result.token);
        localStorage.setItem('admin_role', result.role || 'admin');
        localStorage.setItem('admin_username', result.username || username);
        persistRememberedAdminAccount(result.username || username);

        const profileResp = await getAdminProfileAPI(result.token);
        if (profileResp.httpStatus !== 200 || profileResp.data?.status !== 'success') {
            clearAdminSession();
            setAuthStatus('登录成功，但管理员信息加载失败，请重新登录。');
            return;
        }

        activeAdminProfile = profileResp.data.data;
        setAuthStatus('登录成功！', '#2ecc71');
        checkPermissions();
        loginOverlay.style.display = 'none';
        mainDashboard.style.display = 'block';
        await fetchRecords();
    } catch {
        setAuthStatus('网络异常，请稍后再试。');
    }
}

function showView(targetView) {
    document.querySelectorAll('.nav-tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.target === targetView));
    document.querySelectorAll('.view-section').forEach((section) => section.classList.toggle('active', section.id === targetView));
}

function renderInsights() {
    const dashboard = document.getElementById('insightsDashboard');
    const sourceData = getLatestRecordPerEmail(filteredRecordsData);
    dashboard.style.display = sourceData.length ? 'grid' : 'none';

    const scores = sourceData.map((item) => extractTotalScore(item)).filter((item) => Number.isFinite(item));
    const passCount = sourceData.filter((item) => item.review_status === '拟录取').length;
    const highCount = scores.filter((score) => score >= 80).length;
    const totalScore = scores.reduce((sum, score) => sum + score, 0);

    document.getElementById('stat-total').innerText = String(sourceData.length);
    document.getElementById('stat-avg-score').innerText = scores.length ? (totalScore / scores.length).toFixed(1) : '0';
    document.getElementById('stat-pass-rate').innerText = sourceData.length ? `${((passCount / sourceData.length) * 100).toFixed(1)}%` : '0%';
    document.getElementById('stat-high-score').innerText = scores.length ? `${((highCount / scores.length) * 100).toFixed(1)}%` : '0%';
}

function renderRecordsTable() {
    recordsTableBody.innerHTML = '';
    const canDeleteRecords = isSuperAdmin();
    const columnCount = canDeleteRecords ? 8 : 7;
    if (!filteredRecordsData.length) {
        recordsTableBody.innerHTML = `<tr><td colspan="${columnCount}" style="text-align:center;color:#7f8c8d;">暂无面试记录</td></tr>`;
        syncRecordBatchControls();
        return;
    }

    filteredRecordsData.forEach((record) => {
        const score = extractTotalScore(record);
        const scoreText = Number.isFinite(score) ? score : '-';
        const scoreBadgeClass = Number.isFinite(score) ? getScoreBadgeClass(score) : 'badge-pending';
        const checked = selectedRecordIds.has(record.id) ? 'checked' : '';
        recordsTableBody.insertAdjacentHTML(
            'beforeend',
            `<tr>
                ${canDeleteRecords ? `<td class="record-select-col"><input type="checkbox" class="record-row-check" data-id="${record.id}" aria-label="选择面试记录 ${escapeHtml(record.session_id || record.user_email || record.id)}" ${checked}></td>` : ''}
                <td>${escapeHtml(record.created_at || '-')}</td>
                <td>${escapeHtml(record.user_email || '-')}</td>
                <td>${escapeHtml(record.session_id || '-')}</td>
                <td><span class="badge ${scoreBadgeClass}">${escapeHtml(scoreText)}</span></td>
                <td><span class="badge ${getFaceBadgeClass(record.face_verify_status)}">${escapeHtml(normalizeFaceStatus(record.face_verify_status))}</span></td>
                <td><span class="badge ${getReviewBadgeClass(record.review_status)}">${escapeHtml(record.review_status || '待复核')}</span></td>
                <td>
                    <button class="btn-view" onclick="window.viewRecordReport(${record.id})">查看详情</button>
                    ${isSuperAdmin() ? `<button class="btn-del" onclick="window.deleteInterviewRecord(${record.id})">删除</button>` : ''}
                </td>
            </tr>`
        );
    });
    syncRecordBatchControls();
}

function applyRecordScoreSort() {
    if (recordScoreSortOrder) {
        filteredRecordsData = sortRecordsByScore(filteredRecordsData, recordScoreSortOrder);
    }
}

function syncRecordScoreSortButton() {
    if (!recordScoreSortBtn) return;
    const isAscending = recordScoreSortOrder === 'asc';
    recordScoreSortBtn.textContent = isAscending ? '成绩升序 ↑' : '成绩降序 ↓';
    recordScoreSortBtn.setAttribute(
        'aria-label',
        isAscending ? '当前按 AI 综合得分升序排列，点击切换为降序' : '按 AI 综合得分降序排列'
    );
    recordScoreSortBtn.classList.toggle('is-active', Boolean(recordScoreSortOrder));
}

function applyRecordFilter() {
    const keyword = (recordSearchInput?.value || '').trim().toLowerCase();
    filteredRecordsData = recordsData.filter((record) => {
        if (!keyword) {
            return true;
        }
        const haystack = [
            record.user_email,
            record.session_id,
            record.review_status,
            record.review_remark,
            record.evaluate_status,
            record.face_verify_status,
            normalizeFaceStatus(record.face_verify_status),
            record.proctoring_risk_level,
            normalizeRiskLevel(record.proctoring_risk_level),
            record.archive_status,
            record.archive_error,
            record.evaluate_error,
            record.created_at,
        ]
            .filter(Boolean)
            .join(' ')
            .toLowerCase();
        return haystack.includes(keyword);
    });
    applyRecordScoreSort();
    selectedRecordIds.clear();
    renderInsights();
    renderRecordsTable();
}

async function fetchRecords() {
    const res = await getAdminRecordsAPI(localStorage.getItem('admin_token'));
    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status !== 'success') {
        alert(res.data?.message || '获取面试记录失败。');
        return;
    }
    recordsData = res.data.data || [];
    applyRecordFilter();
}

function renderDimensions(dimensions) {
    const container = document.getElementById('ui-dimensions');
    container.innerHTML = '';
    dimensions.forEach((item) => {
        const score = Number(item.score ?? 0);
        const percent = Math.max(0, Math.min(100, score <= 20 ? score * 5 : score));
        const tier = getPercentTier(percent);
        container.insertAdjacentHTML(
            'beforeend',
            `<div class="dim-item dim-${tier}">
                <h4><span>${escapeHtml(item.name || '维度')}</span><span class="dim-score">${escapeHtml(score)}</span></h4>
                <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:${percent}%;"></div></div>
                <div class="dim-comment">${escapeHtml(item.comment || '')}</div>
            </div>`
        );
    });
}

function openReportModal() {
    reportContent.style.display = 'flex';
    document.body.classList.add('report-modal-open');
    requestAnimationFrame(() => {
        document.getElementById('closeReportBtn')?.focus({ preventScroll: true });
    });
}

function closeReportModal() {
    const videoPlayer = document.getElementById('ui-video');
    if (videoPlayer && !videoPlayer.paused) {
        videoPlayer.pause();
    }
    reportContent.style.display = 'none';
    document.body.classList.remove('report-modal-open');
}

function renderFaceAudit(record) {
    const statusText = normalizeFaceStatus(record.face_verify_status);
    const riskText = normalizeRiskLevel(record.proctoring_risk_level);
    const eventCount = Number(record.proctoring_event_count || 0);
    const flags = record.proctoring_flags && typeof record.proctoring_flags === 'object' ? record.proctoring_flags : {};
    const events = Array.isArray(record.proctoring_events) ? record.proctoring_events : [];

    document.getElementById('ui-face-audit-summary').innerText = `${statusText} / ${riskText}`;
    document.getElementById('ui-face-status').innerHTML = `<span class="badge ${getFaceBadgeClass(record.face_verify_status)}">${escapeHtml(statusText)}</span>`;
    document.getElementById('ui-face-score').innerText = formatFaceScore(record.face_verify_score);
    document.getElementById('ui-face-time').innerText = record.face_verify_at || '-';
    document.getElementById('ui-proctor-risk').innerHTML = `<span class="badge ${getRiskBadgeClass(record.proctoring_risk_level)}">${escapeHtml(riskText)}</span>`;

    const auditCard = document.querySelector('.face-audit-card');
    let previewContainer = document.getElementById('ui-identity-previews');
    if (auditCard && !previewContainer) {
        previewContainer = document.createElement('div');
        previewContainer.id = 'ui-identity-previews';
        previewContainer.className = 'identity-preview-grid';
        document.getElementById('ui-proctor-flags')?.before(previewContainer);
    }
    if (previewContainer) {
        const previews = [
            { label: '证件照', url: record.identity_doc_url },
            { label: '面试前截图', url: record.face_verify_snapshot_url },
        ].filter((item) => item.url);
        previewContainer.innerHTML = previews.length
            ? previews.map((item) => `
                <figure>
                    <img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.label)}">
                    <figcaption>${escapeHtml(item.label)}</figcaption>
                </figure>
            `).join('')
            : '<div class="proctor-event-empty">暂无身份核验图片</div>';
    }

    if (previewContainer) {
        const recheckPreviews = events
            .filter((event) => ['identity_recheck_passed', 'identity_recheck_failed'].includes(event.event_type) && event.image_url)
            .slice(0, 4)
            .map((event, index) => ({
                label: `${formatFlagName(event.event_type)} ${index + 1}`,
                time: event.created_at || event.client_captured_at || '',
                url: event.image_url,
            }));
        const previews = [
            { label: '证件照', url: record.identity_doc_url },
            { label: '面试前截图', url: record.face_verify_snapshot_url },
            ...recheckPreviews,
        ].filter((item) => item.url);
        previewContainer.innerHTML = previews.length
            ? previews.map((item) => `
                <figure>
                    <img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.label)}">
                    <figcaption>${escapeHtml(item.label)}${item.time ? `<small>${escapeHtml(item.time)}</small>` : ''}</figcaption>
                </figure>
            `).join('')
            : '<div class="proctor-event-empty">暂无身份核验图片</div>';
    }

    const flagsContainer = document.getElementById('ui-proctor-flags');
    const flagEntries = Object.entries(flags).filter(([, count]) => Number(count) > 0);
    flagsContainer.innerHTML = flagEntries.length
        ? flagEntries.map(([flag, count]) => `<span>${escapeHtml(formatFlagName(flag))} × ${escapeHtml(count)}</span>`).join('')
        : '<span>暂无监考异常标记</span>';

    const eventsContainer = document.getElementById('ui-proctor-events');
    if (!events.length) {
        eventsContainer.innerHTML = '<div class="proctor-event-empty">暂无监考事件</div>';
        return;
    }
    eventsContainer.innerHTML = `
        <div class="proctor-event-title">最近监考事件（${eventCount || events.length}）</div>
        ${events.map((event) => `
            <div class="proctor-event-row">
                <span>${escapeHtml(event.created_at || event.client_captured_at || '-')}</span>
                <strong>${escapeHtml(formatFlagName(event.event_type || '-'))}</strong>
                <em class="${getRiskBadgeClass(event.risk_level)}">${escapeHtml(normalizeRiskLevel(event.risk_level))}</em>
            </div>
        `).join('')}
    `;
}

function renderReport(record) {
    currentSelectedRecordId = record.id;
    const score = extractTotalScore(record);
    const parsed = parseInterviewReport(record);

    document.getElementById('ui-email').innerText = record.user_email || '-';
    document.getElementById('ui-time').innerText = record.created_at || '-';
    document.getElementById('ui-session-id').innerText = record.session_id || '-';
    document.getElementById('ui-processing-status').innerText = getProcessingStatus(record);
    document.getElementById('ui-evaluate-status').innerText = record.evaluate_status || '-';
    document.getElementById('ui-archive-status').innerText = record.archive_error
        ? `${record.archive_status || '-'} (${record.archive_error})`
        : (record.archive_status || '-');
    const normalizedScore = Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
    const scoreNumber = document.getElementById('ui-total-score');
    scoreNumber.innerText = String(normalizedScore);
    const scoreCard = scoreNumber.closest('.score-circle-container');
    if (scoreCard) {
        scoreCard.style.setProperty('--score-angle', `${normalizedScore * 3.6}deg`);
        scoreCard.dataset.scoreTier = getScoreTier(normalizedScore);
    }
    renderDimensions(parsed.dimensions || []);
    renderFaceAudit(record);
    document.getElementById('ui-advantages').innerHTML = (parsed.advantages || []).length
        ? parsed.advantages.map((item) => `<li>${escapeHtml(item)}</li>`).join('')
        : '<li>暂无</li>';
    document.getElementById('ui-improvements').innerHTML = (parsed.improvements || []).length
        ? parsed.improvements.map((item) => `<li>${escapeHtml(item)}</li>`).join('')
        : '<li>暂无</li>';

    const videoPlayer = document.getElementById('ui-video');
    const downloadBtn = document.getElementById('ui-download-av');
    const avPath = record.av_path || record.video_path || record.audio_path || '';
    if (avPath) {
        videoPlayer.src = avPath;
        downloadBtn.href = avPath;
        downloadBtn.style.display = 'inline-block';
    } else {
        videoPlayer.removeAttribute('src');
        downloadBtn.style.display = 'none';
    }

    const chatHistory = escapeHtml(record.chat_history || '暂无').replaceAll('\n', '<br>');
    document.getElementById('ui-chat-history').innerHTML = chatHistory;
    document.getElementById('reviewStatus').value = record.review_status || '待复核';
    document.getElementById('reviewRemark').value = record.review_remark || '';

    openReportModal();
}

async function saveReview() {
    if (!currentSelectedRecordId) {
        return;
    }
    const status = document.getElementById('reviewStatus').value;
    const remark = document.getElementById('reviewRemark').value;
    const res = await updateRecordReviewAPI(localStorage.getItem('admin_token'), currentSelectedRecordId, status, remark);
    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status === 'success') {
        const item = recordsData.find((record) => record.id === currentSelectedRecordId);
        if (item) {
            item.review_status = status;
            item.review_remark = remark;
        }
        applyRecordFilter();
        alert('保存成功');
        return;
    }
    alert(res.data?.message || '保存失败');
}

async function removeInterviewRecord(recordId) {
    if (!requireSuperAdmin('该用户权限不足，只有超级管理员可以删除面试记录。')) {
        return;
    }
    const record = recordsData.find((item) => item.id === recordId);
    if (!record) {
        alert('记录不存在或已被筛选隐藏');
        return;
    }

    if (!confirm(`确定要删除这条面试记录吗？\n考生邮箱：${record.user_email || '-'}\n会话ID：${record.session_id || '-'}`)) {
        return;
    }

    const res = await deleteRecordAPI(localStorage.getItem('admin_token'), recordId);
    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status === 'success') {
        recordsData = recordsData.filter((item) => item.id !== recordId);
        selectedRecordIds.delete(recordId);
        if (currentSelectedRecordId === recordId) {
            currentSelectedRecordId = null;
            closeReportModal();
        }
        applyRecordFilter();
        alert(res.data.message || '删除成功');
        return;
    }
    alert(res.data?.message || '删除失败');
}

async function deleteSelectedInterviewRecords() {
    if (!requireSuperAdmin('该用户权限不足，只有超级管理员可以批量删除面试记录。')) {
        return;
    }
    const ids = [...selectedRecordIds];
    if (!ids.length) {
        alert('请先选择要删除的面试记录');
        return;
    }

    const preview = ids
        .slice(0, 5)
        .map((id) => {
            const record = recordsData.find((item) => item.id === id);
            return `${record?.user_email || '-'} / ${record?.session_id || id}`;
        })
        .join('\n');
    const suffix = ids.length > 5 ? `\n等 ${ids.length} 条记录` : '';
    if (!confirm(`确定要批量删除选中的 ${ids.length} 条面试记录吗？\n${preview}${suffix}`)) {
        return;
    }

    const token = localStorage.getItem('admin_token');
    batchDeleteRecordsBtn.disabled = true;
    batchDeleteRecordsBtn.textContent = '删除中...';
    try {
        const res = await batchDeleteRecordsAPI(token, ids);
        if (handleAuthFailure(res.httpStatus)) {
            return;
        }

        if (res.data?.status === 'success') {
            const deletedIds = new Set(res.data.deleted_ids || ids);
            finishDeletedRecords(deletedIds, res.data.message || `已删除 ${deletedIds.size} 条面试记录`);
            return;
        }

        const fallback = await deleteRecordsIndividually(token, ids);
        if (fallback.deletedIds.size) {
            finishDeletedRecords(
                fallback.deletedIds,
                fallback.failedIds.length
                    ? `已删除 ${fallback.deletedIds.size} 条，${fallback.failedIds.length} 条删除失败`
                    : `已删除 ${fallback.deletedIds.size} 条面试记录`
            );
            return;
        }

        alert(res.data?.message || fallback.message || '批量删除失败');
    } catch (error) {
        const fallback = await deleteRecordsIndividually(token, ids);
        if (fallback.deletedIds.size) {
            finishDeletedRecords(
                fallback.deletedIds,
                fallback.failedIds.length
                    ? `已删除 ${fallback.deletedIds.size} 条，${fallback.failedIds.length} 条删除失败`
                    : `已删除 ${fallback.deletedIds.size} 条面试记录`
            );
            return;
        }
        alert(fallback.message || error?.message || '批量删除失败');
    } finally {
        syncRecordBatchControls();
    }
}

function finishDeletedRecords(deletedIds, message) {
    recordsData = recordsData.filter((item) => !deletedIds.has(item.id));
    selectedRecordIds.clear();
    if (currentSelectedRecordId && deletedIds.has(currentSelectedRecordId)) {
        currentSelectedRecordId = null;
        closeReportModal();
    }
    applyRecordFilter();
    alert(message);
}

async function deleteRecordsIndividually(token, ids) {
    const deletedIds = new Set();
    const failedIds = [];
    let message = '';
    for (const id of ids) {
        const res = await deleteRecordAPI(token, id);
        if (handleAuthFailure(res.httpStatus)) {
            return { deletedIds, failedIds: ids.filter((item) => !deletedIds.has(item)), message: '登录已失效' };
        }
        if (res.data?.status === 'success') {
            deletedIds.add(id);
        } else {
            failedIds.push(id);
            message = res.data?.message || message;
        }
    }
    return { deletedIds, failedIds, message };
}

function openQuestionModal(question = null) {
    editingQuestionId = question?.id ?? null;
    modalTitle.innerText = question ? '编辑题目' : '新增题目';
    qCategoryInput.value = question?.category || '个人基本情况与留学动机';
    qContentInput.value = question?.content || '';
    questionModal.style.display = 'flex';
}

function closeQuestionModal() {
    questionModal.style.display = 'none';
    editingQuestionId = null;
    qContentInput.value = '';
}

function syncSelectAllQuestionsCheckbox() {
    if (!selectAllQuestionsCheckbox) {
        return;
    }
    selectAllQuestionsCheckbox.checked = questionsData.length > 0 && selectedQuestionIds.size === questionsData.length;
}

function renderQuestionsTable() {
    const tbody = document.getElementById('questionsTableBody');
    tbody.innerHTML = '';
    if (!questionsData.length) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#7f8c8d;">暂无题目数据</td></tr>';
        syncSelectAllQuestionsCheckbox();
        return;
    }

    questionsData.forEach((question) => {
        const checked = selectedQuestionIds.has(question.id) ? 'checked' : '';
        tbody.insertAdjacentHTML(
            'beforeend',
            `<tr>
                <td><input type="checkbox" class="question-row-check" data-id="${question.id}" ${checked}></td>
                <td><span class="badge badge-score-mid" style="font-size:13px;">${escapeHtml(question.category)}</span></td>
                <td style="line-height:1.5;">${escapeHtml(question.content)}</td>
                <td>
                    <button class="btn-edit" onclick="window.editQuestion(${question.id})">编辑</button>
                    <button class="btn-del" onclick="window.deleteQuestion(${question.id})">删除</button>
                </td>
            </tr>`
        );
    });

    document.querySelectorAll('.question-row-check').forEach((checkbox) => {
        checkbox.addEventListener('change', (event) => {
            const id = Number(event.target.dataset.id);
            if (event.target.checked) {
                selectedQuestionIds.add(id);
            } else {
                selectedQuestionIds.delete(id);
            }
            syncSelectAllQuestionsCheckbox();
        });
    });
    syncSelectAllQuestionsCheckbox();
}

async function fetchQuestions() {
    const res = await getQuestionsAPI(localStorage.getItem('admin_token'));
    if (res.status === 'success') {
        questionsData = res.data || [];
        selectedQuestionIds.clear();
        renderQuestionsTable();
        return;
    }
    if (res.detail) {
        alert('登录已失效或无权限，请重新登录。');
        clearAdminSession();
        location.reload();
        return;
    }
    alert(res.message || '获取题库失败。');
}

async function saveQuestion() {
    const category = qCategoryInput.value;
    const content = qContentInput.value.trim();
    if (!content) {
        alert('题目不能为空');
        return;
    }
    saveQBtn.innerText = '保存中...';
    const res = await saveQuestionAPI(localStorage.getItem('admin_token'), editingQuestionId, category, content);
    saveQBtn.innerText = '保存';
    if (res.status === 'success') {
        closeQuestionModal();
        await fetchQuestions();
        return;
    }
    alert(res.message || '保存失败');
}

async function removeQuestion(id) {
    const res = await deleteQuestionAPI(localStorage.getItem('admin_token'), id);
    if (res.status === 'success') {
        selectedQuestionIds.delete(id);
        await fetchQuestions();
        return;
    }
    alert(res.message || '删除失败');
}

async function deleteSelectedQuestions() {
    const ids = [...selectedQuestionIds];
    if (!ids.length) {
        alert('请先勾选要删除的题目');
        return;
    }
    const res = await batchDeleteQuestionsAPI(localStorage.getItem('admin_token'), ids);
    if (res.status === 'success') {
        alert(res.message || `已删除 ${ids.length} 道题目`);
        await fetchQuestions();
        return;
    }
    alert(res.message || '批量删除失败，请稍后重试');
}

async function fetchPrompts() {
    const res = await getPromptsAPI(localStorage.getItem('admin_token'));
    if (res.status === 'success') {
        document.getElementById('basePromptInput').value = res.data.base_prompt || '';
        document.getElementById('evalPromptInput').value = res.data.eval_prompt || '';
        return;
    }
    if (res.detail) {
        alert('该用户权限不足，无法访问提示词微调模块。');
        return;
    }
    alert(res.message || '获取提示词失败。');
}

async function savePrompts() {
    if (!requireSuperAdmin('该用户权限不足，无法访问提示词微调模块。')) {
        return;
    }
    const basePrompt = document.getElementById('basePromptInput').value;
    const evalPrompt = document.getElementById('evalPromptInput').value;
    if (!evalPrompt.includes('{transcript}')) {
        alert('量化评估 Prompt 中必须包含 {transcript} 占位符。');
        return;
    }
    const button = document.getElementById('savePromptsBtn');
    button.innerText = '保存中...';
    const res = await savePromptsAPI(localStorage.getItem('admin_token'), basePrompt, evalPrompt);
    button.innerText = '保存设定并立即生效';
    if (res.status === 'success') {
        alert(res.message || '保存成功');
        return;
    }
    alert(res.message || '保存失败');
}

function openAdminUserModal(mode, admin = null) {
    editingAdminId = admin?.id ?? null;
    adminUserModal.dataset.mode = mode;
    adminUserModal.style.display = 'flex';
    const isCreateMode = mode === 'create';
    adminUserModalTitle.innerText = isCreateMode ? '新增管理员' : '编辑管理员';
    adminUserModalHint.innerText = isCreateMode
        ? '创建后可立即用于后台登录。用户名创建后不可修改，其他信息后续可以更新。'
        : '可修改显示名、邮箱和角色。若需调整密码，请使用“重置密码”。';
    adminUserUsernameInput.value = admin?.username || '';
    adminUserDisplayNameInput.value = admin?.raw_display_name || '';
    adminUserEmailInput.value = admin?.raw_email || '';
    adminUserRoleSelect.value = admin?.role || 'admin';
    adminUserPasswordInput.value = '';
    adminUserUsernameInput.disabled = !isCreateMode;
    adminUserPasswordField.style.display = isCreateMode ? 'block' : 'none';
    saveAdminUserBtn.innerText = isCreateMode ? '保存创建' : '保存修改';
}

function closeAdminUserModal() {
    adminUserModal.style.display = 'none';
    editingAdminId = null;
    adminUserPasswordInput.value = '';
    adminUserModalHint.innerText = '';
}

function openResetAdminPasswordModal(admin) {
    resettingAdminId = admin?.id ?? null;
    resetAdminPasswordTitle.innerText = `重置密码 - ${admin?.username || '管理员'}`;
    resetAdminPasswordHint.innerText = admin?.display_name ? `当前管理员：${admin.display_name}` : '';
    resetAdminPasswordInput.value = '';
    resetAdminPasswordModal.style.display = 'flex';
}

function closeResetAdminPasswordModal() {
    resetAdminPasswordModal.style.display = 'none';
    resettingAdminId = null;
    resetAdminPasswordInput.value = '';
    resetAdminPasswordHint.innerText = '';
}

function renderAdminUsersTable() {
    if (!adminsTableBody) {
        return;
    }
    adminsTableBody.innerHTML = '';
    if (!adminUsersData.length) {
        adminsTableBody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#7f8c8d;">暂无管理员数据</td></tr>';
        return;
    }

    const currentAdminId = activeAdminProfile?.admin_id ?? activeAdminProfile?.id ?? null;
    adminUsersData.forEach((admin) => {
        const nextActionLabel = admin.status === 'active' ? '禁用账号' : '启用账号';
        const toggleClass = admin.status === 'active' ? 'account-toggle-danger' : 'account-toggle-success';
        const canToggle = !(currentAdminId && currentAdminId === admin.id);
        adminsTableBody.insertAdjacentHTML(
            'beforeend',
            `<tr>
                <td><b>${escapeHtml(admin.username)}</b></td>
                <td>${escapeHtml(admin.display_name)}</td>
                <td>${escapeHtml(admin.email)}</td>
                <td><span class="badge ${admin.role === 'super_admin' ? 'badge-score-high' : 'badge-score-mid'}">${escapeHtml(admin.role)}</span></td>
                <td><span class="badge ${admin.status === 'active' ? 'badge-pass' : 'badge-fail'}">${escapeHtml(admin.status)}</span></td>
                <td>${escapeHtml(admin.last_login_at)}</td>
                <td>
                    <div class="admin-row-actions">
                    <button class="btn-edit" onclick="window.editAdminUser(${admin.id})">编辑</button>
                    <button class="btn-view" onclick="window.resetAdminPasswordForAdmin(${admin.id})">重置密码</button>
                    <button class="btn-del ${toggleClass}" style="${canToggle ? '' : 'opacity:0.5;cursor:not-allowed;'}" ${canToggle ? `onclick="window.toggleAdminUserStatus(${admin.id})"` : 'disabled'}>${nextActionLabel}</button>
                    </div>
                </td>
            </tr>`
        );
    });
}

function renderAdminLoginRecordsTable() {
    if (!adminLoginRecordsBody) {
        return;
    }
    adminLoginRecordsBody.innerHTML = '';
    if (!adminLoginRecordsData.length) {
        adminLoginRecordsBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#7f8c8d;">暂无登录日志</td></tr>';
        return;
    }
    adminLoginRecordsData.forEach((record) => {
        adminLoginRecordsBody.insertAdjacentHTML(
            'beforeend',
            `<tr>
                <td>${escapeHtml(record.created_at || '-')}</td>
                <td>${escapeHtml(record.username || '-')}</td>
                <td><span class="badge ${record.login_status === 'success' ? 'badge-pass' : 'badge-fail'}">${escapeHtml(record.login_status || '-')}</span></td>
                <td>${escapeHtml(record.client_ip || '-')}</td>
            </tr>`
        );
    });
}

function renderAdminActionLogsTable() {
    if (!adminActionLogsBody) {
        return;
    }
    adminActionLogsBody.innerHTML = '';
    if (!adminActionLogsData.length) {
        adminActionLogsBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#7f8c8d;">暂无操作日志</td></tr>';
        return;
    }
    adminActionLogsData.forEach((record) => {
        adminActionLogsBody.insertAdjacentHTML(
            'beforeend',
            `<tr>
                <td>${escapeHtml(record.created_at || '-')}</td>
                <td>${escapeHtml(record.username_snapshot || '-')}</td>
                <td>${escapeHtml(record.action || '-')}</td>
                <td>${escapeHtml(record.detail || '-')}</td>
            </tr>`
        );
    });
}

async function fetchAdminUsers() {
    if (!isSuperAdmin()) {
        return;
    }
    const res = await getAdminUsersAPI(localStorage.getItem('admin_token'));
    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status === 'success') {
        adminUsersData = (res.data.data || []).map(normalizeAdminRow);
        renderAdminUsersTable();
        return;
    }
    alert(res.data?.message || '获取管理员列表失败');
}

async function fetchAdminLoginRecords() {
    if (!isSuperAdmin()) {
        return;
    }
    const res = await getAdminLoginRecordsAPI(localStorage.getItem('admin_token'));
    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status === 'success') {
        adminLoginRecordsData = res.data.data || [];
        renderAdminLoginRecordsTable();
    }
}

async function fetchAdminActionLogs() {
    if (!isSuperAdmin()) {
        return;
    }
    const res = await getAdminActionLogsAPI(localStorage.getItem('admin_token'));
    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status === 'success') {
        adminActionLogsData = res.data.data || [];
        renderAdminActionLogsTable();
    }
}

async function refreshAdminUserManagement() {
    await Promise.all([fetchAdminUsers(), fetchAdminLoginRecords(), fetchAdminActionLogs()]);
}

async function saveAdminUser() {
    if (!requireSuperAdmin()) {
        return;
    }
    const mode = adminUserModal.dataset.mode || 'create';
    const username = adminUserUsernameInput.value.trim();
    const display_name = adminUserDisplayNameInput.value.trim();
    const email = adminUserEmailInput.value.trim();
    const role = adminUserRoleSelect.value;

    if (!username) {
        alert('管理员账号不能为空');
        return;
    }
    if (!role) {
        alert('请选择角色');
        return;
    }

    const isCreateMode = mode === 'create';
    if (isCreateMode && !adminUserPasswordInput.value.trim()) {
        alert('密码不能为空');
        return;
    }

    saveAdminUserBtn.disabled = true;
    saveAdminUserBtn.innerText = isCreateMode ? '保存创建' : '保存修改';
    const res = isCreateMode
        ? await createAdminUserAPI(localStorage.getItem('admin_token'), {
            username,
            password: adminUserPasswordInput.value.trim(),
            role,
            display_name,
            email,
        })
        : await updateAdminUserAPI(localStorage.getItem('admin_token'), editingAdminId, { role, display_name, email });
    saveAdminUserBtn.disabled = false;

    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status === 'success') {
        alert(res.data.message || '保存成功');
        closeAdminUserModal();
        await refreshAdminUserManagement();
        return;
    }
    alert(res.data?.message || '保存失败');
}

async function resetAdminPassword() {
    if (!requireSuperAdmin()) {
        return;
    }
    const newPassword = resetAdminPasswordInput.value.trim();
    if (!newPassword) {
        alert('请输入新密码');
        return;
    }
    confirmResetAdminPasswordBtn.disabled = true;
    confirmResetAdminPasswordBtn.innerText = '重置密码';
    const res = await resetAdminPasswordAPI(localStorage.getItem('admin_token'), resettingAdminId, newPassword);
    confirmResetAdminPasswordBtn.disabled = false;
    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status === 'success') {
        alert(res.data.message || '密码已重置');
        closeResetAdminPasswordModal();
        await refreshAdminUserManagement();
        return;
    }
    alert(res.data?.message || '重置密码失败，请稍后重试');
}

async function toggleAdminUserStatus(adminId) {
    if (!requireSuperAdmin()) {
        return;
    }
    const admin = adminUsersData.find((item) => item.id === adminId);
    if (!admin) {
        return;
    }
    const nextStatus = admin.status === 'active' ? 'disabled' : 'active';
    if (!confirm(`确定要将 ${admin.username} 的状态切换为 ${nextStatus} 吗？`)) {
        return;
    }
    const res = await toggleAdminStatusAPI(localStorage.getItem('admin_token'), adminId, nextStatus);
    if (handleAuthFailure(res.httpStatus)) {
        return;
    }
    if (res.data?.status === 'success') {
        alert(res.data.message || '状态已更新');
        await refreshAdminUserManagement();
        return;
    }
    alert(res.data?.message || '更新失败');
}

function exportCsv() {
    let csv = 'data:text/csv;charset=utf-8,\uFEFF面试时间,考生邮箱,会话ID,得分,状态,备注\n';
    getLatestRecordPerEmail(filteredRecordsData).forEach((record) => {
        csv += `${record.created_at},${record.user_email},${record.session_id},${extractTotalScore(record) ?? ''},${record.review_status || ''},${(record.review_remark || '').replace(/\n|,/g, ' ')}\n`;
    });
    const link = document.createElement('a');
    link.href = encodeURI(csv);
    link.download = '面试成绩表.csv';
    link.click();
}

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

function ensureHtml2PdfReady() {
    if (window.html2pdf) return Promise.resolve();
    if (!html2pdfLoadPromise) {
        html2pdfLoadPromise = loadScriptOnce('https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js');
    }
    return html2pdfLoadPromise;
}

async function exportPdf() {
    const actionButtons = document.getElementById('reportActionButtons');
    const reportDialog = reportContent.querySelector('.report-dialog') || reportContent;
    actionButtons.style.display = 'none';
    reportContent.classList.add('report-exporting');
    try {
        await new Promise((resolve) => requestAnimationFrame(resolve));
        await ensureHtml2PdfReady();
        await html2pdf()
            .set({ margin: 10, filename: '面试报告.pdf', html2canvas: { scale: 2 }, jsPDF: { format: 'a4' } })
            .from(reportDialog)
            .save();
    } catch (error) {
        console.error('导出 PDF 失败:', error);
        alert('导出 PDF 失败，请稍后重试。');
    } finally {
        reportContent.classList.remove('report-exporting');
        actionButtons.style.display = 'flex';
    }
}

window.viewRecordReport = (recordId) => {
    const record = recordsData.find((item) => item.id === recordId);
    if (!record) {
        alert('记录不存在或已被筛选隐藏');
        return;
    }
    renderReport(record);
};

window.editQuestion = (questionId) => {
    const question = questionsData.find((item) => item.id === questionId);
    if (question) {
        openQuestionModal(question);
    }
};

window.deleteQuestion = async (questionId) => {
    await removeQuestion(questionId);
};

window.deleteInterviewRecord = async (recordId) => {
    await removeInterviewRecord(recordId);
};

window.editAdminUser = (adminId) => {
    if (!requireSuperAdmin()) {
        return;
    }
    const admin = adminUsersData.find((item) => item.id === adminId);
    if (admin) {
        openAdminUserModal('edit', admin);
    }
};

window.resetAdminPasswordForAdmin = (adminId) => {
    if (!requireSuperAdmin()) {
        return;
    }
    const admin = adminUsersData.find((item) => item.id === adminId);
    if (admin) {
        openResetAdminPasswordModal(admin);
    }
};

window.toggleAdminUserStatus = async (adminId) => {
    await toggleAdminUserStatus(adminId);
};

const adminLoginButton = document.getElementById('adminLoginBtn');
const adminUsernameInput = document.getElementById('adminUsername');
const adminPasswordInput = document.getElementById('adminPassword');
const adminPasswordToggle = document.getElementById('adminPasswordToggle');
const adminRememberButton = document.getElementById('adminRememberAccountBtn');

function isAdminRememberEnabled() {
    return localStorage.getItem(ADMIN_REMEMBER_ENABLED_KEY) !== 'false';
}

function setAdminRememberButtonState(enabled) {
    if (!adminRememberButton) {
        return;
    }
    adminRememberButton.dataset.state = enabled ? 'on' : 'off';
    adminRememberButton.setAttribute('aria-pressed', String(enabled));
    adminRememberButton.setAttribute('aria-label', enabled ? '已开启记住账号' : '已关闭记住账号');
    adminRememberButton.title = enabled ? '登录成功后会保存管理员账号' : '不会保存管理员账号';
}

function hydrateAdminRememberAccount() {
    const enabled = isAdminRememberEnabled();
    setAdminRememberButtonState(enabled);
    if (enabled && adminUsernameInput && !adminUsernameInput.value) {
        adminUsernameInput.value = localStorage.getItem(ADMIN_REMEMBERED_ACCOUNT_KEY) || '';
    }
}

function persistRememberedAdminAccount(username) {
    if (!isAdminRememberEnabled()) {
        localStorage.removeItem(ADMIN_REMEMBERED_ACCOUNT_KEY);
        return;
    }
    if (username) {
        localStorage.setItem(ADMIN_REMEMBERED_ACCOUNT_KEY, username);
    }
}

function toggleAdminRememberAccount() {
    const nextEnabled = !isAdminRememberEnabled();
    localStorage.setItem(ADMIN_REMEMBER_ENABLED_KEY, nextEnabled ? 'true' : 'false');
    setAdminRememberButtonState(nextEnabled);
    if (!nextEnabled) {
        localStorage.removeItem(ADMIN_REMEMBERED_ACCOUNT_KEY);
        return;
    }
    persistRememberedAdminAccount(adminUsernameInput?.value.trim() || '');
}

if (adminLoginButton) {
    adminLoginButton.onclick = loginAdmin;
}

if (adminRememberButton) {
    adminRememberButton.onclick = toggleAdminRememberAccount;
}

if (adminPasswordToggle && adminPasswordInput) {
    adminPasswordToggle.onclick = () => {
        const shouldShow = adminPasswordInput.type === 'password';
        adminPasswordInput.type = shouldShow ? 'text' : 'password';
        adminPasswordToggle.setAttribute('aria-label', shouldShow ? '隐藏密码' : '显示密码');
    };
}

document.getElementById('adminLoginOverlay')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        if (event.target?.closest?.('#adminRememberAccountBtn')) {
            return;
        }
        event.preventDefault();
        loginAdmin();
    }
});
document.getElementById('logoutBtn').onclick = () => {
    clearAdminSession();
    location.reload();
};
document.getElementById('saveReviewBtn').onclick = saveReview;
document.getElementById('closeReportBtn').onclick = closeReportModal;
document.getElementById('exportCsvBtn').onclick = exportCsv;
document.getElementById('exportPdfBtn').onclick = exportPdf;
document.getElementById('savePromptsBtn').onclick = savePrompts;

if (recordSearchBtn) {
    recordSearchBtn.onclick = applyRecordFilter;
}
if (recordSearchResetBtn) {
    recordSearchResetBtn.onclick = () => {
        recordSearchInput.value = '';
        recordScoreSortOrder = null;
        syncRecordScoreSortButton();
        applyRecordFilter();
    };
}
if (recordScoreSortBtn) {
    recordScoreSortBtn.onclick = () => {
        recordScoreSortOrder = recordScoreSortOrder === 'desc' ? 'asc' : 'desc';
        filteredRecordsData = sortRecordsByScore(filteredRecordsData, recordScoreSortOrder);
        syncRecordScoreSortButton();
        renderRecordsTable();
    };
    syncRecordScoreSortButton();
}
if (recordSearchInput) {
    recordSearchInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            applyRecordFilter();
        }
    });
}
if (selectAllRecordsCheckbox) {
    selectAllRecordsCheckbox.addEventListener('change', (event) => {
        selectedRecordIds.clear();
        if (event.target.checked) {
            visibleRecordIds().forEach((id) => selectedRecordIds.add(id));
        }
        renderRecordsTable();
    });
}
if (recordsTableBody) {
    recordsTableBody.addEventListener('change', (event) => {
        const checkbox = event.target.closest?.('.record-row-check');
        if (!checkbox) {
            return;
        }
        const id = Number(checkbox.dataset.id);
        if (!Number.isFinite(id)) {
            return;
        }
        if (checkbox.checked) {
            selectedRecordIds.add(id);
        } else {
            selectedRecordIds.delete(id);
        }
        syncRecordBatchControls();
    });
}
if (batchDeleteRecordsBtn) {
    batchDeleteRecordsBtn.onclick = deleteSelectedInterviewRecords;
    syncRecordBatchControls();
}

if (addQuestionBtn) {
    addQuestionBtn.onclick = () => openQuestionModal();
}
if (cancelQBtn) {
    cancelQBtn.onclick = closeQuestionModal;
}
if (saveQBtn) {
    saveQBtn.onclick = saveQuestion;
}
if (questionModal) {
    questionModal.addEventListener('click', (event) => {
        if (event.target === questionModal) {
            closeQuestionModal();
        }
    });
}
if (selectAllQuestionsCheckbox) {
    selectAllQuestionsCheckbox.addEventListener('change', (event) => {
        selectedQuestionIds.clear();
        if (event.target.checked) {
            questionsData.forEach((question) => selectedQuestionIds.add(question.id));
        }
        renderQuestionsTable();
    });
}
if (batchDeleteQuestionsBtn) {
    batchDeleteQuestionsBtn.onclick = deleteSelectedQuestions;
}

if (refreshAdminUsersBtn) {
    refreshAdminUsersBtn.onclick = refreshAdminUserManagement;
}
if (refreshAdminLoginRecordsBtn) {
    refreshAdminLoginRecordsBtn.onclick = fetchAdminLoginRecords;
}
if (refreshAdminActionLogsBtn) {
    refreshAdminActionLogsBtn.onclick = fetchAdminActionLogs;
}
if (addAdminBtn) {
    addAdminBtn.onclick = () => {
        if (!requireSuperAdmin()) {
            return;
        }
        openAdminUserModal('create');
    };
}
if (cancelAdminUserBtn) {
    cancelAdminUserBtn.onclick = closeAdminUserModal;
}
if (saveAdminUserBtn) {
    saveAdminUserBtn.onclick = saveAdminUser;
}
if (adminUserModal) {
    adminUserModal.addEventListener('click', (event) => {
        if (event.target === adminUserModal) {
            closeAdminUserModal();
        }
    });
}
if (cancelResetAdminPasswordBtn) {
    cancelResetAdminPasswordBtn.onclick = closeResetAdminPasswordModal;
}
if (confirmResetAdminPasswordBtn) {
    confirmResetAdminPasswordBtn.onclick = resetAdminPassword;
}
if (resetAdminPasswordModal) {
    resetAdminPasswordModal.addEventListener('click', (event) => {
        if (event.target === resetAdminPasswordModal) {
            closeResetAdminPasswordModal();
        }
    });
}

if (reportContent) {
    reportContent.addEventListener('click', (event) => {
        if (event.target === reportContent) {
            closeReportModal();
        }
    });
}

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && reportContent?.style.display !== 'none') {
        closeReportModal();
    }
});

if (navMenu) {
    navMenu.addEventListener('click', async (event) => {
        const tab = event.target.closest('.nav-tab');
        if (!tab) {
            return;
        }
        const targetView = tab.dataset.target;
        if (targetView === 'view-prompts' && !isSuperAdmin()) {
            alert('该用户权限不足，无法访问提示词微调模块。');
            return;
        }
        if (targetView === 'view-admin-users' && !isSuperAdmin()) {
            alert('该用户权限不足，无法访问用户管理模块。');
            return;
        }

        showView(targetView);
        if (targetView === 'view-questions' && !questionsData.length) {
            await fetchQuestions();
        }
        if (targetView === 'view-prompts' && !document.getElementById('basePromptInput').value) {
            await fetchPrompts();
        }
        if (targetView === 'view-admin-users') {
            await refreshAdminUserManagement();
        }
    });
}

hydrateAdminRememberAccount();
restoreSession();
