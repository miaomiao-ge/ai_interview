const PAGE_SIZE = 13;
const TOKEN_KEY = 'ai_interviewer_token';

const state = { scale: [], items: [], answers: {}, page: 0 };

function appBasePath() {
  const path = window.location.pathname || '';
  return path === '/interview' || path.startsWith('/interview/') ? '/interview' : '';
}

function authHeaders() {
  const token = localStorage.getItem(TOKEN_KEY) || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api(path, options = {}) {
  const response = await fetch(`/api/user/assessment${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(options.headers || {}) },
  });
  return response.json();
}

function answeredCount() {
  return Object.keys(state.answers).length;
}

function updateProgress() {
  const total = state.items.length || 53;
  document.getElementById('assessProgressText').textContent = `${answeredCount()} / ${total}`;
  document.getElementById('assessBar').style.width = `${(answeredCount() / total) * 100}%`;
}

function renderPage() {
  const start = state.page * PAGE_SIZE;
  const slice = state.items.slice(start, start + PAGE_SIZE);
  const container = document.getElementById('assessItems');

  container.innerHTML = slice.map((item) => `
    <div class="assess-item">
      <h3>${item.no}. ${item.text}</h3>
      <div class="assess-options">
        ${state.scale.map((point) => `
          <label><input type="radio" name="q${item.no}" value="${point.value}"
            ${state.answers[item.no] === point.value ? 'checked' : ''}>${point.text}</label>
        `).join('')}
      </div>
    </div>
  `).join('');

  container.querySelectorAll('input[type=radio]').forEach((input) => {
    input.addEventListener('change', (event) => {
      state.answers[event.target.name.slice(1)] = Number(event.target.value);
      updateProgress();
    });
  });

  document.getElementById('prevBtn').disabled = state.page === 0;
  const lastPage = start + PAGE_SIZE >= state.items.length;
  document.getElementById('nextBtn').hidden = lastPage;
  document.getElementById('submitBtn').hidden = !lastPage;
  updateProgress();
}

async function loadInstrument() {
  const data = await api('/bsi53?locale=zh');
  if (data.status !== 'success') {
    document.getElementById('assessStatus').textContent = data.message || '加载失败，请重新登录后再试';
    return false;
  }
  state.scale = data.scale;
  state.items = data.items;
  if (data.answers) {
    Object.entries(data.answers).forEach(([no, value]) => { state.answers[no] = Number(value); });
  }
  if (data.assessment_status === 'submitted') {
    document.getElementById('assessStatus').textContent = '你已完成心理测评，可以返回准备面试。';
  }
  return true;
}

document.getElementById('consentBox').addEventListener('change', (event) => {
  document.getElementById('startBtn').disabled = !event.target.checked;
});

document.getElementById('startBtn').addEventListener('click', async () => {
  document.getElementById('assessConsent').hidden = true;
  document.getElementById('assessBody').hidden = false;
  if (await loadInstrument()) renderPage();
});

document.getElementById('prevBtn').addEventListener('click', () => {
  if (state.page > 0) {
    state.page -= 1;
    renderPage();
  }
});

document.getElementById('nextBtn').addEventListener('click', () => {
  state.page += 1;
  renderPage();
  api('/draft', {
    method: 'PUT',
    body: JSON.stringify({ answers: state.answers, consent_version: 'v1' }),
  }).catch(() => {});
});

document.getElementById('submitBtn').addEventListener('click', async () => {
  const statusEl = document.getElementById('assessStatus');
  if (answeredCount() !== state.items.length) {
    statusEl.textContent = '还有题目未作答，请返回补充完整。';
    return;
  }
  statusEl.textContent = '提交中…';
  const result = await api('/submit', {
    method: 'POST',
    body: JSON.stringify({ answers: state.answers, consent_version: 'v1' }),
  });
  if (result.status !== 'success') {
    statusEl.textContent = result.message || '提交失败，请重试';
    return;
  }
  statusEl.textContent = '提交成功，正在进行面试准备…';
  const returnTo = sessionStorage.getItem('assessment_return_to') || `${appBasePath()}/`;
  sessionStorage.removeItem('assessment_return_to');
  setTimeout(() => { window.location.href = returnTo; }, 800);
});
