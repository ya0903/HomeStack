const API_BASE = '';
// For local dev with separate servers, set API_BASE = 'http://localhost:8000'

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  document.getElementById('toastContainer').appendChild(el);
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('show')));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 280);
  }, 3800);
}

function initTheme() {
  const saved = localStorage.getItem('hs-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = saved === 'dark' ? '🌙' : '☀️';
}

function getUsedHostPorts() {
  const ports = new Set();
  state.containers.forEach(c => {
    for (const m of (c.Ports || '').matchAll(/(?:[\d.]+|:::):(\d+)->/g)) ports.add(m[1]);
  });
  return ports;
}

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
  containers: [],
  stacks: [],
  plugins: [],
  health: null,
  authConfig: { mode: 'local', login_url: '/', local_auth_enabled: true },
  token: localStorage.getItem('homeStackToken') || '',
  user: JSON.parse(localStorage.getItem('homeStackUser') || 'null'),
  editingStack: null,
};

// ── Plugin registry ───────────────────────────────────────────────────────────
const pluginRegistry = {
  panels: {},        // id → { title, html }
  sidebarItems: [],  // { icon, label, panelId }
  stackActions: [],  // { label, callback }
  eventListeners: {}, // event → [callback]
};

const PluginAPI = {
  /** Register a new full-panel view accessible from the sidebar */
  registerPanel(id, title, htmlContent) {
    pluginRegistry.panels[id] = { title, html: htmlContent };
    const container = document.getElementById('pluginPanels');
    const existing = document.getElementById(`view-plugin-${id}`);
    if (existing) existing.remove();
    const section = document.createElement('section');
    section.className = 'panel hidden';
    section.id = `view-plugin-${id}`;
    section.innerHTML = `<div class="panel-header"><h2>${escapeHtml(title)}</h2></div>${htmlContent}`;
    container.appendChild(section);
  },

  /** Add a nav item in the sidebar linking to a registered panel */
  registerSidebarItem(icon, label, panelId) {
    pluginRegistry.sidebarItems.push({ icon, label, panelId });
    const nav = document.querySelector('.sidebar-nav');
    const btnId = `plugin-nav-${panelId}`;
    if (document.getElementById(btnId)) return;
    const btn = document.createElement('button');
    btn.className = 'nav-btn';
    btn.id = btnId;
    btn.dataset.view = `plugin-${panelId}`;
    btn.innerHTML = `<span class="nav-icon">${icon}</span> ${escapeHtml(label)}`;
    btn.addEventListener('click', () => switchView(`plugin-${panelId}`));
    nav.appendChild(btn);
  },

  /** Add a button to every stack card — callback receives the stack name */
  registerStackAction(label, callback) {
    pluginRegistry.stackActions.push({ label, callback });
  },

  /** Subscribe to app events: stackDeployed, stackDeleted, containerImported */
  onEvent(event, callback) {
    if (!pluginRegistry.eventListeners[event]) pluginRegistry.eventListeners[event] = [];
    pluginRegistry.eventListeners[event].push(callback);
  },

  /** Make an authenticated API call to the HomeStack backend */
  fetch(path, options = {}) {
    return api(path, options);
  },

  /** Show a toast notification */
  toast(msg, type = 'info') {
    toast(msg, type);
  },

  /** Read current app state (stacks, containers, templates, health) */
  getState() {
    return {
      stacks: state.stacks,
      containers: state.containers,
      templates: state.templates,
      health: state.health,
      user: state.user,
    };
  },
};

function emitPluginEvent(event, data) {
  (pluginRegistry.eventListeners[event] || []).forEach(cb => {
    try { cb(data); } catch { /* plugin error — don't crash the app */ }
  });
}

async function loadPlugins() {
  try {
    const plugins = await api('/api/plugins');
    state.plugins = plugins;
    for (const plugin of plugins) {
      if (!plugin.enabled) continue;
      await loadPluginAssets(plugin);
    }
    renderPlugins();
  } catch { /* plugins are non-critical */ }
}

async function loadPluginAssets(plugin) {
  try {
    if (plugin.styles) {
      const styleId = `plugin-style-${plugin.id}`;
      if (!document.getElementById(styleId)) {
        const link = document.createElement('link');
        link.id = styleId;
        link.rel = 'stylesheet';
        link.href = `/api/plugins/${encodeURIComponent(plugin.id)}/assets/${encodeURIComponent(plugin.styles)}`;
        document.head.appendChild(link);
      }
    }
    if (plugin.entry) {
      const scriptUrl = `/api/plugins/${encodeURIComponent(plugin.id)}/assets/${encodeURIComponent(plugin.entry)}`;
      const scriptId = `plugin-script-${plugin.id}`;
      if (document.getElementById(scriptId)) return;
      // Use dynamic import so plugins can use ES module syntax
      const mod = await import(scriptUrl);
      if (typeof mod.init === 'function') {
        mod.init(PluginAPI);
      } else if (typeof mod.default === 'function') {
        mod.default(PluginAPI);
      }
      // Mark as loaded
      const marker = document.createElement('meta');
      marker.id = scriptId;
      document.head.appendChild(marker);
    }
  } catch (err) {
    console.warn(`[HomeStack] Failed to load plugin "${plugin.id}":`, err);
  }
}

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
  const u = state.user;
  els.currentUser.textContent = u ? u.username : 'Not signed in';
  els.currentRole.textContent = u ? u.role : 'Guest';
  els.authModeBadge.textContent = `Auth mode: ${state.authConfig.mode}`;
  const avatar = document.getElementById('userAvatar');
  if (avatar) avatar.textContent = u ? u.username.slice(0, 2).toUpperCase() : '?';
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
  const customOpt = '<option value="__custom__">-- Custom (paste docker-compose) --</option>';
  els.templateSelect.innerHTML = customOpt + state.templates
    .map(t => `<option value="${t.id}">${t.name} (${t.source})</option>`)
    .join('');
  if (!els.templateSelect.value) {
    els.templateSelect.value = '__custom__';
  }
  if (!state.editingStack) applyTemplateDefaults();
}

function applyTemplateDefaults() {
  const tpl = activeTemplate();
  if (tpl) {
    if (!els.stackName.value) els.stackName.value = tpl.id;
    if (!els.installPath.value) els.installPath.value = `/opt/homelab/${tpl.default_install_subdir}`;
  }
  renderDynamicFields();
}

function renderDynamicFields(existing = {}) {
  const isCustom = els.templateSelect.value === '__custom__';
  document.getElementById('customComposeField').classList.toggle('hidden', !isCustom);

  const tpl = activeTemplate();
  if (!tpl || isCustom) {
    els.dynamicFields.innerHTML = '';
    els.volumeBindings.innerHTML = '';
    return;
  }

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

function renderStacks(filter = '') {
  const term = filter.toLowerCase();
  const filtered = term
    ? state.stacks.filter(s => s.stack_name.toLowerCase().includes(term) || (s.template_id || '').toLowerCase().includes(term))
    : state.stacks;

  if (!filtered.length) {
    els.stacksList.innerHTML = `<div class="card">${term ? 'No stacks match your search.' : 'No stacks deployed yet.'}</div>`;
    return;
  }

  els.stacksList.innerHTML = filtered.map(stack => {
    const containers = stack.runtime?.containers || [];
    const running = stack.runtime?.running;
    const name = escapeHtml(stack.stack_name);
    const dotClass = running ? 'dot-success' : (stack.runtime?.available === false ? 'dot-muted' : 'dot-danger');
    const badgeClass = running ? 'badge-success' : 'badge-danger';
    const summary = escapeHtml(stack.runtime?.summary || 'Unknown');
    const cTags = containers.map(c => {
      const cState = String(c.State || '').toLowerCase();
      return `<span class="container-tag ${cState === 'running' ? 'tag-ok' : 'tag-stopped'}">${escapeHtml(c.Service || c.Name || 'container')}</span>`;
    }).join('') || '';
    return `
      <div class="stack-card">
        <div class="stack-card-header">
          <div class="stack-card-title">
            <span class="status-dot ${dotClass}"></span>
            <strong>${name}</strong>
            <span class="badge ${badgeClass}">${summary}</span>
          </div>
          <div class="stack-card-meta">
            <span class="meta-item">🧩 ${escapeHtml(stack.template_id || 'custom')}</span>
            <span class="meta-item">📁 ${escapeHtml(stack.install_path || '—')}</span>
            <span class="meta-item" id="disk-${name}">
              <button class="btn-ghost btn-xs" data-action="diskusage" data-stack-name="${name}">Check disk</button>
            </span>
          </div>
          ${cTags ? `<div class="container-tags">${cTags}</div>` : ''}
        </div>
        <div class="stack-card-actions">
          <button class="btn-sm" data-action="edit" data-stack-name="${name}">Edit</button>
          <button class="btn-sm btn-success" data-action="start" data-stack-name="${name}">▶ Start</button>
          <button class="btn-sm btn-warning" data-action="stop" data-stack-name="${name}">⏹ Stop</button>
          <button class="btn-sm" data-action="restart" data-stack-name="${name}">↺ Restart</button>
          <button class="btn-sm btn-accent" data-action="update" data-stack-name="${name}">⬆ Update</button>
          <button class="btn-sm btn-ghost" data-action="logs" data-stack-name="${name}">📋 Logs</button>
          <button class="btn-sm btn-danger" data-action="delete" data-stack-name="${name}">🗑 Delete</button>
        </div>
        <details class="stack-logs">
          <summary>Last action output</summary>
          <pre id="logs-${name}">Logs appear here.</pre>
        </details>
      </div>
    `;
  }).join('');
}

async function refreshStacks() {
  const stacks = await api('/api/stacks');
  state.stacks = stacks;
  renderStacks(document.getElementById('stackSearch')?.value || '');
}

els.stacksList.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const stackName = btn.dataset.stackName;
  if (action === 'edit') await editStack(stackName);
  else if (action === 'logs') await viewLogs(stackName);
  else if (action === 'delete') await deleteStack(stackName);
  else if (action === 'update') await pullAndRedeployStack(stackName);
  else if (action === 'diskusage') await checkDiskUsage(stackName);
  else await stackAction(stackName, action);
});

function renderSystemStatus() {
  if (!state.health) return;
  const dockerOk = state.health.docker_available;
  const composeOk = state.health.compose_available;
  const term = (document.getElementById('containerSearch')?.value || '').toLowerCase();
  const filtered = term
    ? state.containers.filter(c =>
        (c.Names || c.Name || '').toLowerCase().includes(term) ||
        (c.Image || '').toLowerCase().includes(term))
    : state.containers;

  const containerRows = filtered.map(c => {
    const rawName = (c.Names || c.Name || '').replace(/^\//, '');
    const name = escapeHtml(rawName);
    const image = escapeHtml(c.Image || '');
    const status = escapeHtml(c.State || c.Status || '');
    const ports = escapeHtml(c.Ports || '');
    const stateClass = (c.State || '').toLowerCase() === 'running' ? 'ok' : 'danger';
    const managed = state.stacks.some(s => s.stack_name === rawName);
    const importBtn = managed
      ? '<span class="hint">Managed</span>'
      : `<button class="small" data-action="import" data-container-name="${name}">Import</button>`;
    return `<tr>
      <td style="padding:0.3em 0.6em">${name}</td>
      <td style="padding:0.3em 0.6em">${image}</td>
      <td style="padding:0.3em 0.6em" class="${stateClass}">${status}</td>
      <td style="padding:0.3em 0.6em">${ports}</td>
      <td style="padding:0.3em 0.6em">${importBtn}</td>
    </tr>`;
  }).join('') || `<tr><td colspan="5" class="hint" style="padding:0.6em">${term ? 'No containers match search.' : 'No containers found (Docker may be unavailable)'}</td></tr>`;

  els.systemStatus.innerHTML = `
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">Docker</div>
        <div class="stat-value ${dockerOk ? 'ok' : 'danger'}">${dockerOk ? '✓' : '✗'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Compose</div>
        <div class="stat-value ${composeOk ? 'ok' : 'danger'}">${composeOk ? '✓' : '✗'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Auth mode</div>
        <div class="stat-value" style="font-size:1rem">${escapeHtml(state.authConfig.mode)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Volumes</div>
        <div class="stat-value">${state.volumes.length}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Templates</div>
        <div class="stat-value">${state.templates.length}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Containers</div>
        <div class="stat-value">${state.containers.length}</div>
      </div>
    </div>
    <h3 style="margin-bottom:0.6rem">All containers on this host${term ? ` — ${filtered.length} shown` : ` (${filtered.length})`}</h3>
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr>
          <th>Name</th><th>Image</th><th>State</th><th>Ports</th><th>Actions</th>
        </tr></thead>
        <tbody>${containerRows}</tbody>
      </table>
    </div>
  `;
}

async function refreshAll() {
  els.statusBox.textContent = 'Refreshing data...';
  try {
    const [health, templates, volumes, containers] = await Promise.all([
      api('/api/health'),
      api('/api/templates'),
      api('/api/volumes'),
      api('/api/containers'),
    ]);
    state.health = health;
    state.templates = templates;
    state.volumes = volumes;
    state.containers = containers;
    renderTemplates();
    renderDynamicFields();
    renderSystemStatus();
    await refreshStacks();
    await loadPlugins();
    els.statusBox.textContent = 'Ready.';
  } catch (err) {
    if (state.authConfig.mode === 'local' && String(err.message).toLowerCase().includes('token')) clearAuth();
    els.statusBox.textContent = `Refresh failed: ${err.message}`;
  }
}

async function deployStack() {
  if (els.templateSelect.value === '__custom__') {
    const composeContent = document.getElementById('customCompose').value.trim();
    const stackName = els.stackName.value.trim();
    const installPath = els.installPath.value.trim();
    if (!composeContent) { els.statusBox.textContent = 'Paste docker-compose content first.'; return; }
    if (!stackName) { els.statusBox.textContent = 'Stack name is required.'; return; }
    if (!installPath) { els.statusBox.textContent = 'Install path is required.'; return; }
    const usedPorts = getUsedHostPorts();
    const conflicts = [...composeContent.matchAll(/"(\d+):\d+"/g)].map(m => m[1]).filter(p => usedPorts.has(p));
    if (conflicts.length && !confirm(`Port(s) ${conflicts.join(', ')} are already in use by other containers. Deploy anyway?`)) return;
    els.statusBox.textContent = 'Deploying custom stack...';
    try {
      const data = await api('/api/deploy/raw', {
        method: 'POST',
        body: JSON.stringify({ stack_name: stackName, install_path: installPath, compose_content: composeContent }),
      });
      els.statusBox.textContent = JSON.stringify(data, null, 2);
      emitPluginEvent('stackDeployed', data);
      await refreshStacks();
    } catch (err) {
      els.statusBox.textContent = `Deploy failed: ${err.message}`;
    }
    return;
  }
  const payload = collectPayload();
  els.statusBox.textContent = 'Deploying stack...';
  try {
    const data = await api('/api/deploy', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    els.statusBox.textContent = JSON.stringify(data, null, 2);
    emitPluginEvent('stackDeployed', data);
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
    toast(msg, 'success');
    els.statusBox.textContent = msg;
    const logBox = document.getElementById(`logs-${stackName}`);
    if (logBox) logBox.textContent = JSON.stringify(data, null, 2);
    await refreshStacks();
  } catch (err) {
    toast(`Action failed: ${err.message}`, 'error');
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
    emitPluginEvent('stackDeleted', { stack_name: stackName });
    await refreshStacks();
  } catch (err) {
    els.statusBox.textContent = `Delete failed: ${err.message}`;
  }
}

async function pullAndRedeployStack(stackName) {
  toast(`Pulling latest images for ${stackName}…`, 'info');
  els.statusBox.textContent = `Pulling latest images for ${stackName}...`;
  try {
    const data = await api(`/api/stacks/${stackName}/pull`, { method: 'POST' });
    toast(data.message || 'Stack updated.', 'success');
    els.statusBox.textContent = JSON.stringify(data, null, 2);
    const logBox = document.getElementById(`logs-${stackName}`);
    if (logBox) logBox.textContent = JSON.stringify(data, null, 2);
    await refreshStacks();
  } catch (err) {
    toast(`Update failed: ${err.message}`, 'error');
    els.statusBox.textContent = `Update failed: ${err.message}`;
  }
}

async function checkDiskUsage(stackName) {
  const el = document.getElementById(`disk-${stackName}`);
  if (el) el.textContent = 'Checking…';
  try {
    const data = await api(`/api/stacks/${stackName}/diskusage`);
    if (el) el.textContent = data.disk_usage || 'N/A';
  } catch (err) {
    if (el) el.textContent = 'Error';
  }
}

async function importContainer(containerName) {
  if (!confirm(`Import "${containerName}" as a HomeStack-managed stack?\n\nThis generates a docker-compose.yml from the running container so you can manage it here.`)) return;
  try {
    await api(`/api/containers/${encodeURIComponent(containerName)}/import`, { method: 'POST' });
    toast(`Imported "${containerName}" as a stack.`, 'success');
    els.statusBox.textContent = `Imported "${containerName}" as a stack.`;
    emitPluginEvent('containerImported', { container_name: containerName });
    await refreshStacks();
    renderSystemStatus();
    switchView('stacks');
  } catch (err) {
    toast(`Import failed: ${err.message}`, 'error');
    els.statusBox.textContent = `Import failed: ${err.message}`;
  }
}

function renderPlugins() {
  const list = document.getElementById('pluginsList');
  if (!list) return;
  if (!state.plugins.length) {
    list.innerHTML = '<p class="hint">No plugins installed.</p>';
    return;
  }
  list.innerHTML = state.plugins.map(p => `
    <div class="plugin-card">
      <div class="plugin-card-info">
        <strong>${escapeHtml(p.name || p.id)}</strong>
        <span class="hint">v${escapeHtml(p.version || '?')} ${p.author ? `by ${escapeHtml(p.author)}` : ''}</span>
        ${p.description ? `<p class="plugin-desc">${escapeHtml(p.description)}</p>` : ''}
      </div>
      <div class="plugin-card-actions">
        <span class="badge ${p.enabled ? 'badge-success' : 'badge-muted'}">${p.enabled ? 'Enabled' : 'Disabled'}</span>
        <button class="btn-sm btn-ghost" data-plugin-action="toggle" data-plugin-id="${escapeHtml(p.id)}">${p.enabled ? 'Disable' : 'Enable'}</button>
        <button class="btn-sm btn-danger" data-plugin-action="uninstall" data-plugin-id="${escapeHtml(p.id)}">Uninstall</button>
      </div>
    </div>
  `).join('');
}

async function pluginInstallGit() {
  const url = document.getElementById('pluginGitUrl').value.trim();
  const status = document.getElementById('pluginStatus');
  if (!url) { status.textContent = 'Enter a git URL first.'; return; }
  status.textContent = 'Cloning plugin...';
  try {
    const data = await api('/api/plugins/install/git', {
      method: 'POST',
      body: JSON.stringify({ git_url: url }),
    });
    toast(`Plugin "${data.name || data.id}" installed.`, 'success');
    status.textContent = `Installed: ${data.name || data.id} v${data.version}`;
    document.getElementById('pluginGitUrl').value = '';
    await loadPlugins();
  } catch (err) {
    toast(`Install failed: ${err.message}`, 'error');
    status.textContent = `Install failed: ${err.message}`;
  }
}

async function pluginInstallZip() {
  const fileInput = document.getElementById('pluginZipFile');
  const status = document.getElementById('pluginStatus');
  if (!fileInput.files.length) { status.textContent = 'Select a ZIP file first.'; return; }
  const file = fileInput.files[0];
  status.textContent = 'Uploading plugin...';
  const formData = new FormData();
  formData.append('file', file);
  try {
    const headers = {};
    if (state.authConfig.mode === 'local' && state.token) headers.Authorization = `Bearer ${state.token}`;
    const res = await fetch(`${API_BASE}/api/plugins/install/zip`, { method: 'POST', headers, body: formData, credentials: 'include' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    toast(`Plugin "${data.name || data.id}" installed.`, 'success');
    status.textContent = `Installed: ${data.name || data.id} v${data.version}`;
    fileInput.value = '';
    await loadPlugins();
  } catch (err) {
    toast(`Upload failed: ${err.message}`, 'error');
    status.textContent = `Upload failed: ${err.message}`;
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
  document.getElementById('builderPlaceholders').value = 'NC_CONFIG_PATH\nNC_DATA_PATH';
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
    .split('\n')
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
els.stackName.addEventListener('input', () => {
  const name = els.stackName.value.trim().toLowerCase();
  const warn = document.getElementById('duplicateWarning');
  if (!warn) return;
  const match = state.containers.find(c => {
    const cname = (c.Names || c.Name || '').replace(/^\//, '').toLowerCase();
    return cname === name || cname.startsWith(name + '-') || cname.endsWith('-' + name);
  });
  if (match && name) {
    const cname = (match.Names || match.Name || '').replace(/^\//, '');
    warn.textContent = `Warning: a container named "${cname}" already exists (${match.State || match.Status || 'unknown state'}). Deploying may conflict.`;
    warn.classList.remove('hidden');
  } else {
    warn.classList.add('hidden');
  }
});
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
document.getElementById('pluginInstallGitBtn').addEventListener('click', pluginInstallGit);
document.getElementById('pluginInstallZipBtn').addEventListener('click', pluginInstallZip);

document.getElementById('pluginsList').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-plugin-action]');
  if (!btn) return;
  const action = btn.dataset.pluginAction;
  const pluginId = btn.dataset.pluginId;
  const status = document.getElementById('pluginStatus');
  if (action === 'toggle') {
    try {
      const data = await api(`/api/plugins/${encodeURIComponent(pluginId)}/toggle`, { method: 'POST' });
      toast(`Plugin ${data.enabled ? 'enabled' : 'disabled'}.`, 'info');
      await loadPlugins();
    } catch (err) {
      toast(`Toggle failed: ${err.message}`, 'error');
    }
  } else if (action === 'uninstall') {
    if (!confirm(`Uninstall plugin "${pluginId}"?`)) return;
    try {
      await api(`/api/plugins/${encodeURIComponent(pluginId)}`, { method: 'DELETE' });
      toast(`Plugin "${pluginId}" uninstalled.`, 'success');
      status.textContent = `Plugin "${pluginId}" uninstalled. Reload the page to remove its UI elements.`;
      await loadPlugins();
    } catch (err) {
      toast(`Uninstall failed: ${err.message}`, 'error');
    }
  }
});
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

els.systemStatus.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-action="import"]');
  if (!btn) return;
  await importContainer(btn.dataset.containerName);
});

document.getElementById('stackSearch').addEventListener('input', (e) => {
  renderStacks(e.target.value);
});

document.getElementById('containerSearch').addEventListener('input', () => {
  renderSystemStatus();
});

setInterval(async () => {
  if (!state.user) return;
  try {
    const [containers, stacks] = await Promise.all([
      api('/api/containers').catch(() => state.containers),
      api('/api/stacks').catch(() => state.stacks),
    ]);
    state.containers = containers;
    state.stacks = stacks;
    renderSystemStatus();
    renderStacks(document.getElementById('stackSearch')?.value || '');
  } catch { /* silent */ }
}, 30000);

document.getElementById('themeToggle').addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('hs-theme', next);
  document.getElementById('themeToggle').textContent = next === 'dark' ? '🌙' : '☀️';
});

initTheme();
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
