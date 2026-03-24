const API_BASE = '';
// For local dev with separate servers, set API_BASE = 'http://localhost:8000'

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const state = {
  templates: [],
  volumes: [],
  health: null,
  authConfig: { mode: 'local', login_url: '/', local_auth_enabled: true },
  token: localStorage.getItem('homeStackToken') || '',
  user: JSON.parse(localStorage.getItem('homeStackUser') || 'null'),
  editingStack: null,
};

const els = {
  authOverlay: document.getElementById('authOverlay'),
  authStatus: document.getElementById('authStatus'),
  loginUsername: document.getElementById('loginUsername'),
  loginPassword: document.getElementById('loginPassword'),
  registerUsername: document.getElementById('registerUsername'),
  registerPassword: document.getElementById('registerPassword'),
  templateSelect: document.getElementById('templateSelect'),
  stackName: document.getElementById('stackName'),
  installPath: document.getElementById('installPath'),
  dynamicFields: document.getElementById('dynamicFields'),
  volumeBindings: document.getElementById('volumeBindings'),
  statusBox: document.getElementById('statusBox'),
  stacksList: document.getElementById('stacksList'),
  systemStatus: document.getElementById('systemStatus'),
  currentUser: document.getElementById('currentUser'),
  currentRole: document.getElementById('currentRole'),
  authModeBadge: document.getElementById('authModeBadge'),
  deployBtn: document.getElementById('deployBtn'),
  saveEditBtn: document.getElementById('saveEditBtn'),
  deployTitle: document.getElementById('deployTitle'),
  builderStatus: document.getElementById('builderStatus'),
  localAuthBlock: document.getElementById('localAuthBlock'),
  ssoAuthBlock: document.getElementById('ssoAuthBlock'),
  ssoLoginLink: document.getElementById('ssoLoginLink'),
  ssoRetryBtn: document.getElementById('ssoRetryBtn'),
};

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.authConfig.mode === 'local' && state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' });
  let payload;
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) payload = await res.json();
  else payload = await res.text();
  if (!res.ok) {
    const message = typeof payload === 'string' ? payload : payload.detail || JSON.stringify(payload);
    throw new Error(message);
  }
  return payload;
}

function setAuth(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem('homeStackToken', token);
  localStorage.setItem('homeStackUser', JSON.stringify(user));
  renderUser();
  els.authOverlay.classList.add('hidden');
}

function clearAuth() {
  state.token = '';
  state.user = null;
  localStorage.removeItem('homeStackToken');
  localStorage.removeItem('homeStackUser');
  renderUser();
  if (state.authConfig.mode === 'local') els.authOverlay.classList.remove('hidden');
  else {
    els.authOverlay.classList.remove('hidden');
    els.authStatus.textContent = 'Authelia session required. Use the SSO button and then retry.';
  }
}

function renderUser() {
  els.currentUser.textContent = state.user ? state.user.username : 'Not signed in';
  els.currentRole.textContent = state.user ? state.user.role : 'Guest';
  els.authModeBadge.textContent = `Auth mode: ${state.authConfig.mode}`;
}

function renderAuthMode() {
  const isLocal = state.authConfig.mode === 'local';
  els.localAuthBlock.classList.toggle('hidden', !isLocal);
  els.ssoAuthBlock.classList.toggle('hidden', isLocal);
  els.ssoLoginLink.href = state.authConfig.login_url || '/';
}

function activeTemplate() {
  return state.templates.find(t => t.id === els.templateSelect.value);
}

function renderTemplates() {
  els.templateSelect.innerHTML = state.templates
    .map(t => `<option value="${t.id}">${t.name} (${t.source})</option>`)
    .join('');
  if (state.templates.length && !els.templateSelect.value) {
    els.templateSelect.value = state.templates[0].id;
  }
  if (state.templates.length && !state.editingStack) applyTemplateDefaults();
}

function applyTemplateDefaults() {
  const tpl = activeTemplate();
  if (!tpl) return;
  if (!els.stackName.value) els.stackName.value = tpl.id;
  if (!els.installPath.value) els.installPath.value = `/opt/homelab/${tpl.default_install_subdir}`;
  renderDynamicFields();
}

function renderDynamicFields(existing = {}) {
  const tpl = activeTemplate();
  if (!tpl) return;

  els.dynamicFields.innerHTML = tpl.required_placeholders.map(key => {
    const suffix = key.replace(/^[A-Z]+_/, '').toLowerCase();
    const suggested = existing.placeholders?.[key] || `${els.installPath.value}/${suffix}`;
    return `
      <label>
        ${key}
        <input data-placeholder-key="${key}" type="text" value="${suggested}" />
      </label>
    `;
  }).join('');

  const volumeOptions = ['<option value="">No named volume</option>']
    .concat(state.volumes.map(v => `<option value="${v.name}">${v.name}</option>`));

  els.volumeBindings.innerHTML = tpl.required_placeholders.map(key => `
    <label>
      ${key}
      <select data-volume-key="${key}">
        ${volumeOptions.join('')}
      </select>
    </label>
  `).join('');

  if (existing.named_volume_bindings) {
    document.querySelectorAll('[data-volume-key]').forEach(select => {
      const value = existing.named_volume_bindings[select.dataset.volumeKey] || '';
      select.value = value;
    });
  }
}

function collectPayload() {
  const tpl = activeTemplate();
  const placeholders = {};
  document.querySelectorAll('[data-placeholder-key]').forEach(input => {
    placeholders[input.dataset.placeholderKey] = input.value.trim();
  });
  const namedVolumeBindings = {};
  document.querySelectorAll('[data-volume-key]').forEach(select => {
    if (select.value) namedVolumeBindings[select.dataset.volumeKey] = select.value;
  });
  return {
    template_id: tpl.id,
    stack_name: els.stackName.value.trim(),
    install_path: els.installPath.value.trim(),
    placeholders,
    named_volume_bindings: namedVolumeBindings,
  };
}

async function refreshStacks() {
  const stacks = await api('/api/stacks');
  if (!stacks.length) {
    els.stacksList.innerHTML = '<div class="card">No stacks deployed yet.</div>';
    return;
  }

  els.stacksList.innerHTML = stacks.map(stack => {
    const containers = stack.runtime?.containers || [];
    const runningClass = stack.runtime?.running ? 'ok' : 'danger';
    const name = escapeHtml(stack.stack_name);
    return `
      <div class="card card-grid">
        <div>
          <h3>${name}</h3>
          <div class="kv">
            <strong>Template</strong><span>${escapeHtml(stack.template_id || 'Unknown')}</span>
            <strong>Install path</strong><span>${escapeHtml(stack.install_path || 'Unknown')}</span>
            <strong>Status</strong><span class="${runningClass}">${escapeHtml(stack.runtime?.summary || 'Unknown')}</span>
            <strong>Compose</strong><span>${escapeHtml(stack.compose_path || '')}</span>
          </div>
          <div>
            ${containers.map(c => `<span class="tag">${escapeHtml(c.Service || c.Name || 'container')}: ${escapeHtml(String(c.State || 'unknown'))}</span>`).join('') || '<span class="hint">No container status yet.</span>'}
          </div>
        </div>
        <div>
          <div class="button-row">
            <button data-action="edit" data-stack-name="${escapeHtml(stack.stack_name)}">Edit</button>
            <button data-action="start" data-stack-name="${escapeHtml(stack.stack_name)}">Start</button>
            <button data-action="stop" data-stack-name="${escapeHtml(stack.stack_name)}">Stop</button>
            <button data-action="restart" data-stack-name="${escapeHtml(stack.stack_name)}">Restart</button>
            <button data-action="logs" data-stack-name="${escapeHtml(stack.stack_name)}">Logs</button>
            <button data-action="delete" data-stack-name="${escapeHtml(stack.stack_name)}">Delete</button>
          </div>
          <details>
            <summary>Last action output</summary>
            <pre id="logs-${name}">Logs appear here.</pre>
          </details>
        </div>
      </div>
    `;
  }).join('');
}

els.stacksList.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const stackName = btn.dataset.stackName;
  if (action === 'edit') await editStack(stackName);
  else if (action === 'logs') await viewLogs(stackName);
  else if (action === 'delete') await deleteStack(stackName);
  else await stackAction(stackName, action);
});

function renderSystemStatus() {
  if (!state.health) return;
  els.systemStatus.innerHTML = `
    <div class="grid">
      <div class="card"><strong>Docker available</strong><div>${state.health.docker_available}</div></div>
      <div class="card"><strong>Docker Compose available</strong><div>${state.health.compose_available}</div></div>
      <div class="card"><strong>Auth mode</strong><div>${state.authConfig.mode}</div></div>
      <div class="card"><strong>Named volumes</strong><div>${state.volumes.length}</div></div>
      <div class="card"><strong>Templates</strong><div>${state.templates.length}</div></div>
    </div>
  `;
}

async function refreshAll() {
  els.statusBox.textContent = 'Refreshing data...';
  try {
    const [health, templates, volumes] = await Promise.all([
      api('/api/health'),
      api('/api/templates'),
      api('/api/volumes'),
    ]);
    state.health = health;
    state.templates = templates;
    state.volumes = volumes;
    renderTemplates();
    renderDynamicFields();
    renderSystemStatus();
    await refreshStacks();
    els.statusBox.textContent = 'Ready.';
  } catch (err) {
    if (state.authConfig.mode === 'local' && String(err.message).toLowerCase().includes('token')) clearAuth();
    els.statusBox.textContent = `Refresh failed: ${err.message}`;
  }
}

async function deployStack() {
  const payload = collectPayload();
  els.statusBox.textContent = 'Deploying stack...';
  try {
    const data = await api('/api/deploy', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    els.statusBox.textContent = JSON.stringify(data, null, 2);
    await refreshStacks();
  } catch (err) {
    els.statusBox.textContent = `Deploy failed: ${err.message}`;
  }
}

async function saveEdit() {
  if (!state.editingStack) return;
  const payload = collectPayload();
  els.statusBox.textContent = `Saving changes to ${state.editingStack}...`;
  try {
    const data = await api(`/api/stacks/${state.editingStack}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    els.statusBox.textContent = JSON.stringify(data, null, 2);
    await refreshStacks();
  } catch (err) {
    els.statusBox.textContent = `Save failed: ${err.message}`;
  }
}

async function editStack(stackName) {
  try {
    const stack = await api(`/api/stacks/${stackName}`);
    state.editingStack = stackName;
    els.deployTitle.textContent = `Edit stack: ${stackName}`;
    els.deployBtn.classList.add('hidden');
    els.saveEditBtn.classList.remove('hidden');
    els.templateSelect.value = stack.template_id;
    els.stackName.value = stack.stack_name;
    els.installPath.value = stack.install_path;
    renderDynamicFields(stack);
    switchView('deploy');
    els.statusBox.textContent = `Loaded ${stackName} for editing.`;
  } catch (err) {
    els.statusBox.textContent = `Could not load stack: ${err.message}`;
  }
}

function resetDeployForm() {
  state.editingStack = null;
  els.deployTitle.textContent = 'Deploy a stack';
  els.deployBtn.classList.remove('hidden');
  els.saveEditBtn.classList.add('hidden');
  els.stackName.value = '';
  els.installPath.value = '';
  renderTemplates();
  renderDynamicFields();
  els.statusBox.textContent = 'Ready to deploy a new stack.';
}

async function stackAction(stackName, action) {
  try {
    const data = await api(`/api/stacks/${stackName}/action`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
    const msg = data.message || `Stack ${action} completed.`;
    els.statusBox.textContent = msg;
    const logBox = document.getElementById(`logs-${stackName}`);
    if (logBox) logBox.textContent = JSON.stringify(data, null, 2);
    await refreshStacks();
  } catch (err) {
    els.statusBox.textContent = `Action failed: ${err.message}`;
    const logBox = document.getElementById(`logs-${stackName}`);
    if (logBox) logBox.textContent = `Action failed: ${err.message}`;
  }
}

async function viewLogs(stackName) {
  try {
    const data = await api(`/api/stacks/${stackName}/logs`);
    const logBox = document.getElementById(`logs-${stackName}`);
    if (logBox) logBox.textContent = data.logs;
  } catch (err) {
    const logBox = document.getElementById(`logs-${stackName}`);
    if (logBox) logBox.textContent = `Log fetch failed: ${err.message}`;
  }
}

async function deleteStack(stackName) {
  if (!confirm(`Delete stack "${stackName}"? This will stop its containers.`)) return;
  const deleteData = confirm('Also delete data directories from disk? This cannot be undone.');
  try {
    await api(`/api/stacks/${stackName}?delete_data=${deleteData}`, { method: 'DELETE' });
    els.statusBox.textContent = `Stack "${stackName}" deleted.`;
    await refreshStacks();
  } catch (err) {
    els.statusBox.textContent = `Delete failed: ${err.message}`;
  }
}

async function login() {
  try {
    const data = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: els.loginUsername.value.trim(), password: els.loginPassword.value }),
    });
    setAuth(data.token, data.user);
    els.authStatus.textContent = 'Login successful.';
    await refreshAll();
  } catch (err) {
    els.authStatus.textContent = `Login failed: ${err.message}`;
  }
}

async function register() {
  try {
    const data = await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username: els.registerUsername.value.trim(), password: els.registerPassword.value }),
    });
    setAuth(data.token, data.user);
    els.authStatus.textContent = 'Account created.';
    await refreshAll();
  } catch (err) {
    els.authStatus.textContent = `Registration failed: ${err.message}`;
  }
}

function templateExample() {
  document.getElementById('builderId').value = 'nextcloud-basic';
  document.getElementById('builderName').value = 'Nextcloud Basic';
  document.getElementById('builderDescription').value = 'Example custom template for a Linux friendly Nextcloud deployment.';
  document.getElementById('builderSubdir').value = 'cloud/nextcloud';
  document.getElementById('builderPlaceholders').value = 'NC_CONFIG_PATH
NC_DATA_PATH';
  document.getElementById('builderCompose').value = `services:
  app:
    image: nextcloud:stable
    container_name: {{STACK_NAME}}
    restart: unless-stopped
    ports:
      - "8088:80"
    volumes:
      - {{NC_CONFIG_PATH}}:/var/www/html
      - {{NC_DATA_PATH}}:/var/www/html/data`;
}

async function saveTemplate() {
  const required_placeholders = document.getElementById('builderPlaceholders').value
    .split('
')
    .map(v => v.trim())
    .filter(Boolean);
  try {
    const data = await api('/api/templates', {
      method: 'POST',
      body: JSON.stringify({
        id: document.getElementById('builderId').value.trim(),
        name: document.getElementById('builderName').value.trim(),
        description: document.getElementById('builderDescription').value.trim(),
        default_install_subdir: document.getElementById('builderSubdir').value.trim(),
        required_placeholders,
        compose_template_text: document.getElementById('builderCompose').value,
      }),
    });
    els.builderStatus.textContent = JSON.stringify(data, null, 2);
    await refreshAll();
  } catch (err) {
    els.builderStatus.textContent = `Save failed: ${err.message}`;
  }
}

function switchView(name) {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  document.querySelectorAll('[id^="view-"]').forEach(section => section.classList.add('hidden'));
  document.getElementById(`view-${name}`).classList.remove('hidden');
}

function wireNavigation() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });
  document.querySelectorAll('.auth-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.auth-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.auth-view').forEach(v => v.classList.add('hidden'));
      document.getElementById(`auth-${btn.dataset.authView}`).classList.remove('hidden');
    });
  });
}

els.templateSelect.addEventListener('change', () => renderDynamicFields());
els.installPath.addEventListener('input', () => renderDynamicFields());
document.getElementById('refreshAll').addEventListener('click', refreshAll);
document.getElementById('refreshStacksBtn').addEventListener('click', refreshStacks);
document.getElementById('deployBtn').addEventListener('click', deployStack);
document.getElementById('saveEditBtn').addEventListener('click', saveEdit);
document.getElementById('newStackBtn').addEventListener('click', resetDeployForm);
document.getElementById('logoutBtn').addEventListener('click', clearAuth);
document.getElementById('loginBtn').addEventListener('click', login);
document.getElementById('registerBtn').addEventListener('click', register);
document.getElementById('builderSave').addEventListener('click', saveTemplate);
document.getElementById('builderGenerateExample').addEventListener('click', templateExample);
els.ssoRetryBtn.addEventListener('click', async () => {
  try {
    const me = await api('/api/auth/me');
    state.user = me.user;
    renderUser();
    els.authOverlay.classList.add('hidden');
    await refreshAll();
  } catch (err) {
    els.authStatus.textContent = `SSO check failed: ${err.message}`;
  }
});

wireNavigation();
renderUser();
renderAuthMode();

(async function init() {
  try {
    const config = await api('/api/auth/config');
    state.authConfig = config;
    renderAuthMode();
    renderUser();
  } catch {
    state.authConfig = { mode: 'local', login_url: '/', local_auth_enabled: true };
  }

  if (state.authConfig.mode === 'authelia_proxy') {
    try {
      const me = await api('/api/auth/me');
      state.user = me.user;
      localStorage.setItem('homeStackUser', JSON.stringify(me.user));
      renderUser();
      els.authOverlay.classList.add('hidden');
      await refreshAll();
    } catch {
      els.authOverlay.classList.remove('hidden');
      els.authStatus.textContent = 'This instance is using Authelia SSO. Sign in via the reverse proxy and then press Retry.';
    }
    return;
  }

  if (!state.token) {
    els.authOverlay.classList.remove('hidden');
    return;
  }
  try {
    const me = await api('/api/auth/me');
    state.user = me.user;
    localStorage.setItem('homeStackUser', JSON.stringify(me.user));
    renderUser();
    els.authOverlay.classList.add('hidden');
    await refreshAll();
  } catch {
    clearAuth();
  }
})();
