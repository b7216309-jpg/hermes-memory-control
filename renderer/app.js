'use strict';

import DOMPurify from 'dompurify';
import { marked } from 'marked';
import { createDemoApi } from './demo-api.js';
import { MemoryGraph } from './graph.js';

const api = window.hermesControl || createDemoApi();
const demoMode = !window.hermesControl;
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {
  connected: false,
  probe: null,
  overview: null,
  agency: null,
  schema: null,
  database: 'base',
  configPlugin: 'memory',
  staged: { memory: new Map(), agency: new Map() },
  selectedMemoryTable: 'facts',
  selectedAgencyTable: 'intentions',
  labVisible: false,
  labUnlocked: false,
  graph: null,
};

const MEMORY_TABLES = [
  ['facts','facts'],['topics','topics'],['episodes','episodes'],['sessions','sessions'],
  ['traces','traces'],['journals','journals'],['summaries','summaries'],['preferences','preferences'],
  ['policies','policies'],['contradictions','contradictions'],['history','history'],['links','links'],
  ['evidence','belief evidence'],['working','working memory'],['procedures','procedures'],
  ['prospective','prospective memory'],['autobiographical','autobiographical'],
  ['associations','associations'],['approvals','approvals'],['pending','pending operations'],
];
const AGENCY_TABLES = [['subjective','subjective journal'],['intentions','intentions'],['reflections','reflections'],['decisions','decisions'],['events','event ledger'],['meta','persistent state']];

function h(tag, attrs = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') element.className = value;
    else if (key === 'dataset') Object.assign(element.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') element.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value !== false && value !== null && value !== undefined) element.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

function replace(element, ...children) {
  element.replaceChildren(...children.flat().filter((item) => item !== null && item !== undefined));
}

function short(value, length = 120) {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text && text.length > length ? `${text.slice(0, length - 1)}…` : (text ?? '');
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
}

function setStatus(message, kind = '') {
  $('#status-message').textContent = message;
  $('#top-status').textContent = message;
  const pulse = $('#health-pulse');
  pulse.className = `pulse ${kind}`;
}

function toast(message, kind = 'ok') {
  const node = h('div', { class: `toast ${kind}` }, message);
  $('#toast-stack').append(node);
  setTimeout(() => node.remove(), 4200);
}

async function guarded(label, operation) {
  try {
    setStatus(label, 'warn');
    const result = await operation();
    setStatus(state.connected ? 'connected' : 'ready', state.connected ? 'ok' : '');
    return result;
  } catch (error) {
    const message = error?.message || String(error);
    setStatus('operation failed', 'bad');
    toast(message, 'bad');
    throw error;
  }
}

function addKv(container, key, value, color = '') {
  container.append(h('div', { class: 'kv' }, h('span', { class: 'key' }, key), h('span', { class: `value ${color}` }, value ?? '—')));
}

function panel(title, color = '', wide = false) {
  const body = h('div');
  return { root: h('section', { class: `panel ${wide ? 'wide' : ''}` }, h('div', { class: `panel-title ${color}` }, title), body), body };
}

function healthLine(label, ok, note = '') {
  return h('div', { class: 'health-line' }, h('span', { class: `dot ${ok === true ? 'ok' : ok === false ? 'bad' : 'warn'}` }), h('span', {}, label), h('span', { class: 'key' }, note));
}

async function loadProfiles() {
  const profiles = await guarded('discovering WSL profiles', () => api.profiles());
  const select = $('#profile-select');
  replace(select);
  for (const profile of profiles) {
    const option = h('option', { value: JSON.stringify(profile) }, `${profile.distro} :: ${profile.home}`);
    select.append(option);
  }
  if (!profiles.length) {
    select.append(h('option', { value: '' }, 'No WSL Hermes profile found'));
    $('#connect-button').disabled = true;
  }
  if (demoMode && profiles.length) await connect();
  else setStatus('ready');
}

async function connect() {
  const raw = $('#profile-select').value;
  if (!raw) return;
  const profile = JSON.parse(raw);
  const probe = await guarded('connecting', () => api.connect(profile));
  state.connected = true;
  state.probe = probe;
  $('#status-path').textContent = probe.home;
  $('#refresh-button').disabled = false;
  const databases = $('#database-select');
  replace(databases);
  for (const item of probe.memory.databases || []) {
    databases.append(h('option', { value: item.id, disabled: !item.exists }, `${item.label}${item.size ? ` · ${formatBytes(item.size)}` : ''}${item.exists ? '' : ' · missing'}`));
  }
  databases.disabled = false;
  state.database = databases.value || 'base';
  renderContractAudit();
  await refreshAll();
}

async function refreshAll() {
  if (!state.connected) return;
  const [overview, agency] = await guarded('running health audit', () => Promise.all([
    api.read('memory_overview', { database: state.database }),
    api.read('agency_snapshot', {}),
  ]));
  state.overview = overview;
  state.agency = agency;
  renderDashboard();
  renderAgencyState();
}

function renderDashboard() {
  const grid = $('#dashboard-grid');
  replace(grid);
  const doctor = state.overview?.doctor || {};
  const counts = doctor.source_counts || {};
  const memory = panel('consolidating memory', 'orange');
  memory.body.append(h('div', { class: 'metric' }, counts.facts ?? '—'));
  addKv(memory.body, 'facts', counts.facts);
  addKv(memory.body, 'preferences', counts.preferences);
  addKv(memory.body, 'policies', counts.policies);
  addKv(memory.body, 'sessions', counts.sessions);
  addKv(memory.body, 'intentions', counts.intentions);

  const agency = panel('conscious agency', 'cyan');
  const snapshot = state.agency?.snapshot || {};
  const gates = state.agency?.gates || {};
  addKv(agency.body, 'focus', snapshot.workspace?.focus || '(none)');
  addKv(agency.body, 'active intentions', snapshot.intentions?.length ?? 0);
  addKv(agency.body, 'paused', snapshot.runtime?.paused ? 'yes' : 'no');
  addKv(agency.body, 'reflection', gates.reflection_eligible ? 'eligible' : 'blocked');
  addKv(agency.body, 'proactive speech', gates.speak_eligible || gates.eligible ? 'eligible' : 'blocked');
  addKv(agency.body, 'blocked by', (gates.blocked_by || []).join(', ') || '—');

  const health = panel('integrity & queues', 'green');
  health.body.append(
    healthLine('SQLCipher store opens', doctor.integrity?.[0] === 'ok'),
    healthLine('FTS indexes agree', Object.keys(doctor.fts_mismatches || {}).length === 0),
    healthLine('No dangling references', Object.values(doctor.dangling_references || {}).every((value) => value === 0)),
    healthLine('Durable queue clean', Number(doctor.failed_operations || 0) === 0),
    healthLine('Audit hash chain', state.probe?.control?.audit?.valid === true),
  );

  const runtime = panel('runtime', '');
  addKv(runtime.body, 'Hermes', state.probe?.hermes_version || 'unknown');
  addKv(runtime.body, 'memory plugin', state.probe?.memory?.version || 'missing');
  addKv(runtime.body, 'agency plugin', state.probe?.agency?.version || 'missing');
  addKv(runtime.body, 'database', state.database);
  addKv(runtime.body, 'logical size', formatBytes(doctor.logical_database_size_bytes || doctor.database_size_bytes));
  addKv(runtime.body, 'controller backups', state.probe?.control?.backups ?? 0);

  const policy = panel('privacy & policy', 'amber');
  addKv(policy.body, 'memory encryption', state.probe?.memory?.config?.database_encryption ? 'required' : 'off');
  addKv(policy.body, 'agency encryption', state.probe?.agency?.config?.database_encryption ? 'required' : 'off');
  addKv(policy.body, 'scope', state.probe?.memory?.config?.memory_scope || 'unknown');
  addKv(policy.body, 'retrieval', state.probe?.memory?.config?.retrieval_backend || 'unknown');
  addKv(policy.body, 'agency policy mode', state.probe?.agency?.runtime?.contract?.mode || 'unknown');

  const controls = panel('operator quick actions', '', true);
  const row = h('div', { class: 'inspector-actions' });
  for (const [label, action, payload] of [
    ['memory backup','memory_backup',() => ({ database: state.database })],
    ['agency backup','agency_backup',() => ({})],
    ['pause agency','agency_pause',() => ({ reason: 'Paused from Hermes Control Center' })],
    ['restart gateway','gateway_restart',() => ({})],
  ]) row.append(h('button', { class: `button ${action === 'agency_pause' ? 'danger' : ''}`, onclick: () => mutate(action, payload()) }, label));
  controls.body.append(row);
  grid.append(memory.root, agency.root, health.root, runtime.root, policy.root, controls.root);
}

function fillOptions(select, items) {
  replace(select, ...items.map(([value, label]) => h('option', { value }, label)));
}

function renderTable(table, data, onSelect) {
  replace(table);
  const columns = data.columns || [];
  table.append(h('thead', {}, h('tr', {}, ...columns.map((column) => h('th', {}, column)))));
  const body = h('tbody');
  for (const row of data.rows || []) {
    const tr = h('tr', { onclick: () => {
      body.querySelectorAll('tr').forEach((item) => item.classList.remove('selected'));
      tr.classList.add('selected');
      onSelect(row);
    } });
    for (const column of columns) tr.append(h('td', { title: short(row[column], 1000) }, short(row[column], 180)));
    body.append(tr);
  }
  table.append(body);
}

function renderInspector(container, title, row, actions = []) {
  replace(container);
  if (!row) { container.append(h('div', { class: 'empty' }, 'Select a ledger row to inspect it.')); return; }
  container.append(h('h3', {}, title));
  for (const [key, value] of Object.entries(row)) {
    container.append(h('div', { class: 'field' }, h('label', {}, key), h('div', {}, typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value ?? ''))));
  }
  if (actions.length) container.append(h('div', { class: 'inspector-actions' }, ...actions.map(({ label, className = '', run }) => h('button', { class: `button ${className}`, onclick: run }, label))));
}

function renderMemoryEditor(container, title, row, editable, idField, actions = []) {
  replace(container);
  if (!row) return renderInspector(container);
  container.append(h('h3', {}, title));
  const inputs = new Map();
  for (const [key, value] of Object.entries(row)) {
    const field = h('div', { class: 'field' }, h('label', {}, key));
    if (editable.includes(key)) {
      let input;
      if (['active','pinned'].includes(key)) {
        input = h('input', { type: 'checkbox' }); input.checked = Boolean(Number(value));
      } else {
        const numeric = typeof value === 'number';
        input = h('input', { type: numeric ? 'number' : 'text', value: value ?? '', step: numeric && !Number.isInteger(value) ? 'any' : '1' });
      }
      inputs.set(key, input); field.append(input);
    } else field.append(h('div', {}, typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value ?? '')));
    container.append(field);
  }
  const save = {
    label: 'save changes',
    run: () => {
      const changes = {};
      for (const [key, input] of inputs) {
        const original = row[key];
        let value = input.type === 'checkbox' ? input.checked : input.value;
        if (typeof original === 'number') value = Number(value);
        const normalizedOriginal = ['active','pinned'].includes(key) ? Boolean(Number(original)) : original;
        if (value !== normalizedOriginal) changes[key] = value;
      }
      if (!Object.keys(changes).length) return toast('No field changed', 'bad');
      void mutate('memory_update_item', { database: state.database, table: title, id: row[idField], changes });
    },
  };
  container.append(h('div', { class: 'inspector-actions' }, ...[save, ...actions].map(({ label, className = '', run }) => h('button', { class: `button ${className}`, onclick: run }, label))));
}

async function loadMemoryTable() {
  const tableName = $('#memory-table').value;
  state.selectedMemoryTable = tableName;
  const data = await guarded(`loading ${tableName}`, () => api.read('memory_list', { database: state.database, table: tableName, query: $('#memory-query').value, limit: 200 }));
  renderTable($('#memory-grid'), data, (row) => {
    const actions = [];
    if (tableName === 'facts' && Number(row.active) !== 0) actions.push({ label: 'deactivate', className: 'danger', run: () => mutate('memory_deactivate_fact', { database: state.database, id: row.id }) });
    if (tableName === 'approvals' && row.status === 'pending') {
      actions.push({ label: 'approve', run: () => mutate('memory_resolve_approval', { database: state.database, id: row.id, approved: true, resolution: 'Approved in Control Center' }) });
      actions.push({ label: 'deny', className: 'danger', run: () => mutate('memory_resolve_approval', { database: state.database, id: row.id, approved: false, resolution: 'Denied in Control Center' }) });
    }
    if (tableName === 'prospective' && row.status === 'pending') actions.push({ label: 'complete', run: () => mutate('memory_resolve_intention', { database: state.database, id: row.id, status: 'completed' }) });
    renderMemoryEditor($('#memory-inspector'), tableName, row, data.editable || [], data.id_field || 'id', actions);
  });
}

function renderAgencyState() {
  const container = $('#agency-state');
  replace(container);
  if (!state.agency) { container.append(h('div', { class: 'empty' }, 'Load agency state.')); return; }
  const snapshot = state.agency.snapshot || {};
  const focus = panel('global workspace', 'cyan');
  addKv(focus.body, 'focus', snapshot.workspace?.focus || '(none)');
  addKv(focus.body, 'questions', snapshot.workspace?.questions?.length || 0);
  addKv(focus.body, 'silent ticks', snapshot.runtime?.consecutive_silent_ticks || 0);
  for (const question of snapshot.workspace?.questions || []) {
    focus.body.append(h('div', { class: 'health-line' }, h('span', {}, short(question.question, 120)), h('button', { class: 'button', onclick: () => mutate('agency_resolve_question', { id: question.id }) }, 'resolve')));
  }
  const metrics = snapshot.state_metrics || {};
  const signals = panel('state metrics', 'amber');
  for (const [key, value] of Object.entries(metrics)) {
    let rendered = '—';
    if (value !== null && value !== undefined) {
      const numeric = Number(value);
      rendered = Number.isInteger(numeric) && !key.endsWith('_ratio')
        ? String(numeric)
        : numeric.toFixed(2);
    }
    addKv(signals.body, key, rendered);
  }
  const subjective = panel('subjective experiment', snapshot.subjective?.mode === 'off' ? 'amber' : 'red');
  addKv(subjective.body, 'mode', snapshot.subjective?.mode || 'off');
  addKv(subjective.body, 'protocol', snapshot.subjective?.protocol_version || '—');
  addKv(subjective.body, 'entries', snapshot.subjective?.entries ?? 0);
  addKv(subjective.body, 'models', Object.keys(snapshot.subjective?.models || {}).length);
  addKv(subjective.body, 'continuity links', snapshot.subjective?.continuity_links ?? 0);
  addKv(subjective.body, 'silent samples', snapshot.subjective?.silent_entries ?? 0);
  const gates = panel('proactive gates', state.agency.gates?.eligible ? 'green' : 'red');
  addKv(gates.body, 'speak eligible', state.agency.gates?.speak_eligible || state.agency.gates?.eligible ? 'yes' : 'no');
  addKv(gates.body, 'reflection eligible', state.agency.gates?.reflection_eligible ? 'yes' : 'no');
  addKv(gates.body, 'blocked', (state.agency.gates?.blocked_by || []).join(', ') || '—');
  const cron = h('div', { class: 'inspector-actions' },
    h('button', { class: 'button', onclick: () => mutate('agency_install_cron', {}) }, 'install/update cron'),
    h('button', { class: 'button', onclick: () => mutate('agency_run_cron', {}) }, 'run now'),
    h('button', { class: 'button', onclick: () => mutate('agency_pause_cron', {}) }, 'pause cron'),
    h('button', { class: 'button', onclick: () => mutate('agency_resume_cron', {}) }, 'resume cron'),
    h('button', { class: 'button danger', onclick: () => mutate('agency_remove_cron', {}) }, 'remove cron'),
  );
  container.append(subjective.root, focus.root, signals.root, gates.root, cron);
}

async function loadAgencyTable() {
  const tableName = $('#agency-table').value;
  state.selectedAgencyTable = tableName;
  const data = await guarded(`loading agency ${tableName}`, () => api.read('agency_list', { table: tableName, query: $('#agency-query').value, limit: 200 }));
  renderTable($('#agency-grid'), data, (row) => {
    const actions = [];
    if (tableName === 'intentions' && row.status === 'active') {
      actions.push({ label: 'complete', run: () => mutate('agency_update_intention', { id: row.id, status: 'completed' }) });
      actions.push({ label: 'block', className: 'danger', run: () => mutate('agency_update_intention', { id: row.id, status: 'blocked' }) });
      actions.push({ label: 'cancel', className: 'danger', run: () => mutate('agency_update_intention', { id: row.id, status: 'cancelled' }) });
    }
    if (tableName === 'intentions') {
      actions.push({ label: 'set/clear due', run: () => {
        const dueAt = window.prompt('ISO-8601 deadline (blank clears):', row.due_at || '');
        if (dueAt !== null) void mutate('agency_update_intention', { id: row.id, due_at: dueAt });
      } });
    }
    renderInspector($('#agency-inspector'), tableName, row, actions);
  });
}

async function ensureSchema() {
  if (!state.schema) state.schema = await guarded('loading configuration schema', () => api.read('config_schema', {}));
  renderConfig();
  renderLabConfig();
}

function currentSetting(plugin, item) {
  return state.staged[plugin].has(item.key) ? state.staged[plugin].get(item.key) : item.value;
}

function setSetting(plugin, item, value) {
  if (value === item.value) state.staged[plugin].delete(item.key);
  else state.staged[plugin].set(item.key, value);
  updateStagedCount();
}

function settingInput(plugin, item, rerender) {
  const value = currentSetting(plugin, item);
  if (item.type === 'boolean') {
    const button = h('button', { type: 'button', disabled: item.read_only, class: `switch ${value ? 'on' : ''}`, 'aria-label': `${item.key}: ${value ? 'on' : 'off'}`, onclick: () => { setSetting(plugin, item, !value); rerender(); } });
    return h('div', { class: 'bool-control' }, h('span', {}, value ? 'on' : 'off'), button);
  }
  if (Array.isArray(item.choices)) {
    const select = h('select', { onchange: () => { setSetting(plugin, item, select.value); rerender(); } });
    for (const choice of item.choices) select.append(h('option', { value: choice, selected: choice === value }, choice));
    return select;
  }
  const input = h('input', { value: value ?? '', disabled: item.read_only, type: item.type === 'integer' || item.type === 'number' ? 'number' : 'text', step: item.type === 'integer' ? '1' : item.type === 'number' ? 'any' : undefined });
  input.addEventListener('change', () => {
    let next = input.value;
    if (item.type === 'integer') next = Number.parseInt(next, 10);
    if (item.type === 'number') next = Number.parseFloat(next);
    setSetting(plugin, item, next);
    rerender();
  });
  return input;
}

function configRow(plugin, item, rerender) {
  const changed = state.staged[plugin].has(item.key);
  return h('div', { class: `config-row ${changed ? 'changed' : ''} ${item.lab ? 'lab' : ''}` },
    h('div', {}, h('div', { class: 'config-name' }, item.key), h('div', { class: 'config-desc' }, item.description), changed ? h('div', { class: 'config-desc' }, `saved: ${String(item.value)}`) : null),
    settingInput(plugin, item, rerender),
  );
}

function renderConfig() {
  if (!state.schema) return;
  const plugin = state.configPlugin;
  const filter = $('#config-filter').value.trim().toLowerCase();
  const items = state.schema[plugin].filter((item) => !item.lab && (!filter || `${item.key} ${item.description}`.toLowerCase().includes(filter)));
  replace($('#config-grid'), ...items.map((item) => configRow(plugin, item, renderConfig)));
  updateStagedCount();
}

function renderLabConfig() {
  if (!state.schema) return;
  const container = $('#lab-config');
  replace(container);
  for (const plugin of ['memory','agency']) {
    const items = state.schema[plugin].filter((item) => item.lab);
    if (!items.length) continue;
    container.append(h('div', { class: 'panel-title red' }, plugin));
    for (const item of items) container.append(configRow(plugin, item, renderLabConfig));
    container.append(h('button', { class: 'button danger', onclick: () => applyConfig(plugin, true) }, `preview ${plugin} lab changes`));
  }
}

function updateStagedCount() {
  const count = state.staged.memory.size + state.staged.agency.size;
  $('#staged-count').textContent = `${count} staged`;
}

async function applyConfig(plugin = state.configPlugin, labOnly = false) {
  const all = Object.fromEntries(state.staged[plugin]);
  const labKeys = new Set((state.schema?.[plugin] || []).filter((item) => item.lab).map((item) => item.key));
  const changes = labOnly ? Object.fromEntries(Object.entries(all).filter(([key]) => labKeys.has(key))) : Object.fromEntries(Object.entries(all).filter(([key]) => !labKeys.has(key)));
  if (!Object.keys(changes).length) return toast('No staged settings in this section', 'bad');
  await mutate('config_apply', { plugin, changes });
  for (const [key, value] of Object.entries(changes)) {
    state.staged[plugin].delete(key);
    const item = state.schema[plugin].find((candidate) => candidate.key === key);
    if (item) item.value = value;
  }
  renderConfig(); renderLabConfig();
}

async function loadBackups() {
  const items = await guarded('loading backups', () => api.read('backups_list', {}));
  const container = $('#backups-list');
  replace(container);
  if (!items.length) return container.append(h('div', { class: 'empty' }, 'No controller backups yet.'));
  for (const item of items) {
    const restore = h('button', { class: 'button danger', onclick: () => mutate(item.kind === 'memory' ? 'memory_restore' : 'agency_restore', item.kind === 'memory' ? { database: state.database, backup_id: item.id } : { backup_id: item.id }) }, 'restore');
    container.append(h('div', { class: 'backup-item' }, h('strong', {}, item.kind), h('span', {}, new Date(item.modified).toLocaleString()), h('span', {}, `${item.id} · ${formatBytes(item.size)}`), restore));
  }
}

async function loadAudit() {
  const report = await guarded('verifying audit chain', () => api.read('audit_list', { limit: 200 }));
  $('#audit-integrity').textContent = report.valid ? '✓ hash chain valid' : '✗ HASH CHAIN INVALID';
  $('#audit-integrity').style.color = report.valid ? 'var(--green)' : 'var(--red)';
  const container = $('#audit-list');
  replace(container);
  for (const event of report.events || []) {
    container.append(h('div', { class: 'audit-event' }, h('span', {}, new Date(event.at).toLocaleString()), h('strong', {}, event.operation), h('span', {}, short(event.result, 220)), h('code', {}, String(event.hash).slice(0, 16))));
  }
}

async function loadWiki() {
  const pages = await guarded('loading wiki index', () => api.read('wiki_list', {}));
  const list = $('#wiki-list');
  replace(list);
  if (!pages.length) return list.append(h('div', { class: 'empty' }, 'Wiki export is disabled or empty.'));
  for (const page of pages) list.append(h('button', { onclick: () => openWiki(page.id) }, `${page.title} · ${formatBytes(page.size)}`));
  await openWiki(pages[0].id);
}

async function openWiki(id) {
  const page = await guarded('opening wiki page', () => api.read('wiki_read', { id }));
  const html = marked.parse(page.markdown, { gfm: true, breaks: false });
  $('#wiki-content').innerHTML = DOMPurify.sanitize(html, { USE_PROFILES: { html: true }, FORBID_TAGS: ['style','form','iframe','object','embed'], FORBID_ATTR: ['style'] });
  $('#wiki-content').querySelectorAll('a').forEach((link) => { link.removeAttribute('target'); link.removeAttribute('href'); });
}

async function loadGraph() {
  if (!state.graph) state.graph = new MemoryGraph($('#graph-canvas'), $('#graph-tooltip'), (item) => toast(`${item.type}: ${short(item.label, 180)}`));
  const data = await guarded('building memory graph', () => api.read('memory_graph', { database: state.database, limit: 300 }));
  state.graph.setData(data);
}

function renderContractAudit() {
  const contract = state.probe?.agency?.runtime?.contract;
  const container = $('#contract-audit');
  replace(container);
  if (!contract) return container.append(h('div', { class: 'empty' }, 'Not connected.'));
  container.append(
    h('div', { class: 'contract-check' }, h('span', {}, 'plugin policy mode'), h('span', { class: contract.effective_unrestricted ? 'fail' : 'pass' }, contract.mode || 'unknown')),
    h('div', { class: 'contract-check' }, h('span', {}, 'subjective experiment'), h('span', { class: contract.subjective_experiment?.enabled ? 'fail' : 'pass' }, contract.subjective_experiment?.mode || 'off')),
  );
  for (const [key, value] of Object.entries(contract.checks || {})) {
    container.append(h('div', { class: 'contract-check' }, h('span', {}, key), h('span', { class: value ? 'pass' : 'fail' }, value ? 'yes' : 'no')));
  }
  for (const [key, value] of Object.entries(contract.configured_controls || {})) {
    container.append(h('div', { class: 'contract-check' }, h('span', {}, key), h('span', { class: value ? 'fail' : 'pass' }, value ? 'enabled' : 'disabled')));
  }
  for (const [key, value] of Object.entries(contract.active_guardrails || {})) {
    container.append(h('div', { class: 'contract-check' }, h('span', {}, `stored cron · ${key}`), h('span', { class: value ? 'pass' : 'fail' }, value ? 'active' : 'removed')));
  }
  const core = contract.hermes_core;
  if (core) {
    container.append(
      h('div', { class: 'contract-check' }, h('span', {}, 'Hermes core · delivery wrapper'), h('span', {}, core.delivery_wrapper_present ? 'active upstream' : 'not detected')),
      h('div', { class: 'contract-check' }, h('span', {}, 'Hermes core · per-job override'), h('span', {}, core.per_job_override_supported ? 'supported' : 'not supported')),
    );
  }
}

async function revealLab() {
  state.labVisible = true;
  $('.lab-nav').classList.remove('hidden');
  renderContractAudit();
  await ensureSchema();
  switchView('lab');
  $('.lab-nav').focus();
  toast('Educational Lab revealed. It remains locked.', 'bad');
}

async function unlockLab() {
  const result = await guarded('unlocking educational lab', () => api.unlockLab($('#lab-phrase').value));
  state.labUnlocked = Boolean(result.unlocked);
  $('#lab-status').textContent = state.labUnlocked ? `unlocked until ${new Date(result.expiresAt).toLocaleTimeString()}` : 'locked';
  $('#lab-status').style.color = state.labUnlocked ? 'var(--red)' : 'var(--dim)';
  $('#lab-phrase').value = '';
}

function confirmPlan(plan) {
  return new Promise((resolve) => {
    const dialog = $('#confirm-dialog');
    $('#confirm-risk').textContent = `${plan.risk.toUpperCase()} RISK${plan.labRequired ? ' · LAB REQUIRED' : ''}`;
    $('#confirm-title').textContent = plan.title;
    $('#confirm-summary').textContent = plan.summary;
    $('#confirm-required').textContent = plan.phrase;
    $('#confirm-input').value = '';
    const commit = $('#confirm-commit');
    const onCommit = (event) => {
      event.preventDefault();
      if ($('#confirm-input').value !== plan.phrase) {
        $('#confirm-input').focus();
        toast('Confirmation phrase does not match', 'bad');
        return;
      }
      dialog.close('commit');
    };
    commit.addEventListener('click', onCommit);
    dialog.addEventListener('close', () => { commit.removeEventListener('click', onCommit); resolve(dialog.returnValue === 'commit' ? $('#confirm-input').value : null); }, { once: true });
    dialog.showModal();
    $('#confirm-input').focus();
  });
}

async function mutate(action, payload) {
  if (!state.connected) return toast('Connect to Hermes first', 'bad');
  try {
    const plan = await guarded('building action preview', () => api.preview(action, payload));
    const phrase = await confirmPlan(plan);
    if (!phrase) { setStatus('action cancelled', 'ok'); return null; }
    const result = await guarded('committing audited action', () => api.commit(plan.id, phrase));
    toast(`${plan.title} completed · audit ${result.audit?.hash?.slice(0, 10) || 'recorded'}`);
    if (['memory_update_item','memory_deactivate_fact','memory_resolve_approval','memory_resolve_intention'].includes(action)) await loadMemoryTable();
    if (action.startsWith('agency_') && !action.includes('backup')) { await refreshAll(); await loadAgencyTable(); }
    if (action.includes('backup') || action.includes('restore')) await loadBackups();
    if (action === 'config_apply' || action === 'lab_apply_profile') { state.schema = null; state.probe = await api.read('probe', {}); await ensureSchema(); await refreshAll(); }
    return result;
  } catch {
    return null;
  }
}

function switchView(name) {
  $$('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === name));
  $$('.view').forEach((item) => item.classList.toggle('active', item.id === `view-${name}`));
  if (!state.connected && name !== 'dashboard' && name !== 'lab') return toast('Connect to Hermes from Overview first', 'bad');
  if (name === 'memory') void loadMemoryTable();
  if (name === 'agency') { renderAgencyState(); void loadAgencyTable(); }
  if (name === 'graph') void loadGraph();
  if (name === 'config') void ensureSchema();
  if (name === 'backups') void loadBackups();
  if (name === 'audit') void loadAudit();
  if (name === 'wiki') void loadWiki();
}

function setup() {
  $('#win-min').addEventListener('click', () => api.minimize());
  $('#win-max').addEventListener('click', () => api.maximize());
  $('#win-close').addEventListener('click', () => api.close());
  $$('.nav-item').forEach((item) => item.addEventListener('click', () => switchView(item.dataset.view)));
  $('#connect-button').addEventListener('click', connect);
  $('#refresh-button').addEventListener('click', refreshAll);
  $('#database-select').addEventListener('change', async () => { state.database = $('#database-select').value; await refreshAll(); });
  fillOptions($('#memory-table'), MEMORY_TABLES); fillOptions($('#agency-table'), AGENCY_TABLES);
  $('#memory-load').addEventListener('click', loadMemoryTable); $('#memory-query').addEventListener('keydown', (event) => { if (event.key === 'Enter') void loadMemoryTable(); });
  $('#agency-load').addEventListener('click', loadAgencyTable); $('#agency-query').addEventListener('keydown', (event) => { if (event.key === 'Enter') void loadAgencyTable(); });
  $('#memory-backup').addEventListener('click', () => mutate('memory_backup', { database: state.database }));
  $('#memory-export').addEventListener('click', () => mutate('memory_export', { database: state.database, include_sensitive: false }));
  $('#memory-retry').addEventListener('click', () => mutate('memory_retry_failed', { database: state.database, limit: 100 }));
  $('#memory-maintain').addEventListener('click', () => mutate('memory_maintain', { database: state.database }));
  $('#agency-backup').addEventListener('click', () => mutate('agency_backup', {}));
  $('#agency-pause').addEventListener('click', () => mutate('agency_pause', { reason: 'Paused from Hermes Control Center' }));
  $('#agency-resume').addEventListener('click', () => mutate('agency_resume', {}));
  $('#agency-focus').addEventListener('click', () => { const focus = window.prompt('New persistent focus:'); if (focus !== null) void mutate('agency_focus', { focus, reason: 'Set in Hermes Control Center' }); });
  $('#agency-add').addEventListener('click', () => { const title = window.prompt('New intention:'); if (title) void mutate('agency_add_intention', { title, priority: 50, autonomy: 'propose' }); });
  $('#agency-question').addEventListener('click', () => { const question = window.prompt('New unresolved question:'); if (question) void mutate('agency_add_question', { question }); });
  $('#agency-observation').addEventListener('click', () => { const observation = window.prompt('New inspectable self-observation:'); if (observation) void mutate('agency_add_observation', { observation }); });
  $('#graph-load').addEventListener('click', loadGraph); $('#graph-reset').addEventListener('click', () => state.graph?.reset());
  $$('[data-config-plugin]').forEach((button) => button.addEventListener('click', () => { state.configPlugin = button.dataset.configPlugin; $$('[data-config-plugin]').forEach((item) => item.classList.toggle('active', item === button)); renderConfig(); }));
  $('#config-filter').addEventListener('input', renderConfig); $('#config-apply').addEventListener('click', () => applyConfig());
  $('#backup-memory').addEventListener('click', () => mutate('memory_backup', { database: state.database })); $('#backup-agency').addEventListener('click', () => mutate('agency_backup', {})); $('#backups-load').addEventListener('click', loadBackups);
  $('#audit-load').addEventListener('click', loadAudit);
  $('#lab-unlock').addEventListener('click', unlockLab);
  $('#lab-unrestricted').addEventListener('click', () => mutate('lab_apply_profile', { profile: 'unrestricted_research' }));
  $('#lab-export-sensitive').addEventListener('click', () => mutate('memory_export', { database: state.database, include_sensitive: true }));
  $('#lab-recommended').addEventListener('click', () => mutate('lab_apply_profile', { profile: 'recommended' }));
  let clicks = 0, clickTimer;
  $('#version-trigger').addEventListener('click', () => { clicks += 1; clearTimeout(clickTimer); clickTimer = setTimeout(() => { clicks = 0; }, 4000); if (clicks >= 7) { clicks = 0; void revealLab(); } });
  document.addEventListener('keydown', (event) => { if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'l') void revealLab(); });
  const savedTheme = localStorage.getItem('hmc-theme') || 'gruvbox';
  document.documentElement.dataset.theme = savedTheme; $('#theme-select').value = savedTheme;
  $('#theme-select').addEventListener('change', () => { document.documentElement.dataset.theme = $('#theme-select').value; localStorage.setItem('hmc-theme', $('#theme-select').value); });
  renderInspector($('#memory-inspector')); renderInspector($('#agency-inspector'));
}

setup();
void loadProfiles();
