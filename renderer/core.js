/* ── Hermes Memory Control -- core renderer ── */
'use strict';

const DEFAULTS = {
  db_path:'$HERMES_HOME/consolidating_memory.db',min_hours:24,min_sessions:5,scan_cooldown_seconds:600,
  prefetch_limit:8,max_topic_facts:5,topic_summary_chars:650,session_summary_chars:900,
  prune_after_days:90,episode_body_retention_hours:24,decay_half_life_days:90,decay_min_salience:0.15,
  reconsolidation_window_hours:6,review_intervals_days:'1,3,7,14,30',
  builtin_snapshot_sync_enabled:true,builtin_memory_dir:'$HERMES_HOME/memories',
  builtin_snapshot_user_chars:1375,builtin_snapshot_memory_chars:2200,
  wiki_export_enabled:false,wiki_export_dir:'$HERMES_HOME/consolidating_memory_wiki',
  wiki_export_on_consolidate:true,wiki_export_session_limit:50,wiki_export_topic_limit:100,
  extractor_backend:'hybrid',retrieval_backend:'fts',embedding_candidate_limit:16,
  llm_model:'',llm_base_url:'',llm_timeout_seconds:45,llm_max_input_chars:4000,
  embedding_model:'',embedding_base_url:'',embedding_timeout_seconds:20,
};

let hermesHome = '';
let pluginCfg = {};
let savedPluginCfg = {};

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

function loadApp() { try { return JSON.parse(localStorage.getItem('hmc-settings')||'{}'); } catch { return {}; } }
function saveApp(o) { const c = loadApp(); Object.assign(c, o); localStorage.setItem('hmc-settings', JSON.stringify(c)); }

/* ── theme ── */
const themeSel = $('#theme-sel');
(() => { const t = loadApp().uiTheme || 'gruvbox'; document.documentElement.setAttribute('data-ui-theme', t); themeSel.value = t; })();
themeSel.addEventListener('change', () => { const t = themeSel.value; document.documentElement.setAttribute('data-ui-theme', t); saveApp({ uiTheme: t }); });

/* ── restore path ── */
(() => { const s = loadApp(); if (s.hermesHome) { $('#hermes-path').value = s.hermesHome; hermesHome = s.hermesHome; } })();

/* ── status ── */
function setStatus(t, c) { const el = $('#tb-status'); el.textContent = t; el.style.color = `var(--${c||'fg2'})`; }

/* ── nav ── */
$$('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.nav-btn').forEach(b => b.classList.remove('active'));
    $$('.view').forEach(v => v.classList.remove('active'));
    btn.classList.add('active');
    const v = $(`#${btn.dataset.view}`);
    if (v) v.classList.add('active');
  });
});

/* ── config tabs ── */
$$('.cfg-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.cfg-tab').forEach(b => b.classList.remove('active'));
    $$('.cfg-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const p = $(`#${btn.dataset.cfg}`);
    if (p) p.classList.add('active');
  });
});

/* ── form <-> config ── */
function populateForm() {
  $$('[data-key]').forEach(el => {
    const val = pluginCfg[el.dataset.key] !== undefined ? pluginCfg[el.dataset.key] : DEFAULTS[el.dataset.key];
    if (el.type === 'checkbox') el.checked = !!val;
    else if (el.tagName === 'SELECT') el.value = String(val || '');
    else el.value = val ?? '';
  });
}
function readForm() {
  $$('[data-key]').forEach(el => {
    if (el.type === 'checkbox') pluginCfg[el.dataset.key] = el.checked;
    else if (el.type === 'number') { const v = parseFloat(el.value); if (!isNaN(v)) pluginCfg[el.dataset.key] = v; }
    else pluginCfg[el.dataset.key] = el.value;
  });
}

/* ── DB query helper ── */
async function dbq(type, args) {
  if (!hermesHome) { setStatus('not connected', 'rd'); return null; }
  return api.dbQuery(hermesHome, type, args || {});
}

/* ── connect ── */
async function connect() {
  const p = $('#hermes-path').value.trim();
  if (!p) { setStatus('no path', 'rd'); return; }
  hermesHome = p;
  saveApp({ hermesHome: p });
  setStatus('loading...', 'am');
  $('#sb-path').textContent = p;
  const result = await api.loadConfig(p);
  if (result.error) { setStatus('error', 'rd'); return; }
  pluginCfg = { ...DEFAULTS, ...result.config };
  savedPluginCfg = { ...pluginCfg };
  populateForm();
  setStatus('connected', 'gr');
  $('#sb-config').textContent = result.configPath || 'loaded';
  refreshDash();
}

/* ── dashboard stats ── */
async function refreshDash() {
  const s = await dbq('stats');
  if (!s || s.error) return;
  $('#d-facts').textContent = s.active_facts ?? '--';
  $('#d-inactive').textContent = s.inactive_facts ?? '--';
  $('#d-topics').textContent = s.topics ?? '--';
  $('#d-sessions').textContent = s.sessions ?? '--';
  $('#d-prefs').textContent = s.preferences ?? '--';
  $('#d-policies').textContent = s.policies ?? '--';
  $('#d-summaries').textContent = s.summaries ?? '--';
  $('#d-journals').textContent = s.journals ?? '--';
  $('#d-contra').textContent = s.contradictions ?? '--';
  $('#d-history').textContent = s.history_rows ?? '--';
  $('#d-last-consol').textContent = s.last_consolidation ?? '--';
}

/* ── save / revert config ── */
async function saveConfig() {
  if (!hermesHome) { setStatus('not connected', 'rd'); return; }
  readForm();
  setStatus('saving...', 'am');
  const r = await api.saveConfig(hermesHome, pluginCfg);
  if (r.error) { setStatus('save failed', 'rd'); return; }
  savedPluginCfg = { ...pluginCfg };
  setStatus('saved', 'gr');
}
function revertConfig() { pluginCfg = { ...savedPluginCfg }; populateForm(); setStatus('reverted', 'am'); }

/* ── config presets ── */
function getPresets() { try { return JSON.parse(localStorage.getItem('hmc-presets') || '{}'); } catch { return {}; } }
function setPresets(p) { localStorage.setItem('hmc-presets', JSON.stringify(p)); }

function refreshPresetList() {
  const sel = $('#preset-sel');
  const presets = getPresets();
  sel.innerHTML = '<option value="">-- select --</option>';
  Object.keys(presets).sort().forEach(name => {
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    sel.appendChild(opt);
  });
}

$('#btn-preset-save')?.addEventListener('click', () => {
  const name = $('#preset-name').value.trim();
  if (!name) { setStatus('enter a preset name', 'rd'); return; }
  readForm();
  const presets = getPresets();
  presets[name] = { ...pluginCfg };
  setPresets(presets);
  refreshPresetList();
  $('#preset-sel').value = name;
  $('#preset-name').value = '';
  setStatus(`preset "${name}" saved`, 'gr');
});

$('#btn-preset-load')?.addEventListener('click', () => {
  const name = $('#preset-sel').value;
  if (!name) { setStatus('select a preset', 'rd'); return; }
  const presets = getPresets();
  if (!presets[name]) { setStatus('preset not found', 'rd'); return; }
  pluginCfg = { ...DEFAULTS, ...presets[name] };
  populateForm();
  setStatus(`preset "${name}" loaded (unsaved)`, 'am');
});

$('#btn-preset-delete')?.addEventListener('click', () => {
  const name = $('#preset-sel').value;
  if (!name) { setStatus('select a preset', 'rd'); return; }
  if (!confirm(`Delete preset "${name}"?`)) return;
  const presets = getPresets();
  delete presets[name];
  setPresets(presets);
  refreshPresetList();
  setStatus(`preset "${name}" deleted`, 'rd');
});

refreshPresetList();

/* ── detail panel ── */
function showDetail(title, kvPairs) {
  $('#detail-title').textContent = title;
  const body = $('#detail-body');
  body.innerHTML = '';
  kvPairs.forEach(([k, v, color]) => {
    const d = document.createElement('div');
    d.className = 'kv';
    d.innerHTML = `<span class="k">${esc(k)}</span><span class="v ${color||''}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;word-break:break-all;white-space:normal;text-align:right;">${esc(String(v))}</span>`;
    body.appendChild(d);
  });
  $('#detail-panel').classList.add('open');
}
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

/* ── editable detail panel ── */
const EDIT_FIELDS = {
  fact: {
    editable: ['content','category','subject_key','value_key','importance','confidence','polarity','exclusive'],
    numbers: ['importance','confidence'],
    selects: { category: ['user_pref','project','environment','workflow','general'] },
    booleans: ['exclusive'],
    textareas: ['content'],
    updateType: 'update_fact', deleteType: 'delete_fact', toggleType: 'toggle_fact_active',
    reload: () => loadFacts(),
  },
  topic: {
    editable: ['title','category','importance','summary'],
    numbers: ['importance'],
    selects: { category: ['user_pref','project','environment','workflow','general'] },
    booleans: [],
    textareas: ['summary'],
    updateType: 'update_topic', deleteType: null, toggleType: null,
    reload: () => loadTopics(),
  },
  preference: {
    editable: ['label','value','content','importance'],
    numbers: ['importance'],
    selects: {},
    booleans: [],
    textareas: ['content'],
    updateType: 'update_preference', deleteType: 'delete_preference', toggleType: null,
    reload: () => loadPrefs(),
  },
  policy: {
    editable: ['label','content','importance'],
    numbers: ['importance'],
    selects: {},
    booleans: [],
    textareas: ['content'],
    updateType: 'update_policy', deleteType: 'delete_policy', toggleType: null,
    reload: () => loadPrefs(),
  },
};

function showEditableDetail(entityType, entityId, data) {
  const cfg = EDIT_FIELDS[entityType];
  if (!cfg) { showDetail(entityType + ' #' + entityId, Object.entries(data).map(([k,v]) => [k, v])); return; }

  $('#detail-title').textContent = `${entityType} #${entityId}`;
  const body = $('#detail-body');
  body.innerHTML = '';
  const fields = {};

  Object.entries(data).forEach(([k, v]) => {
    const d = document.createElement('div');
    d.className = 'kv detail-field';
    const isEditable = cfg.editable.includes(k);

    if (!isEditable) {
      d.innerHTML = `<span class="k">${esc(k)}</span><span class="v" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;word-break:break-all;white-space:normal;text-align:right;font-size:10px;">${esc(String(v ?? ''))}</span>`;
    } else if (cfg.selects[k]) {
      const opts = cfg.selects[k].map(o => `<option value="${o}"${o===String(v)?' selected':''}>${o}</option>`).join('');
      d.innerHTML = `<span class="k">${esc(k)}</span><select data-field="${k}">${opts}</select>`;
      fields[k] = () => d.querySelector('select').value;
    } else if (cfg.booleans.includes(k)) {
      const checked = v ? 'checked' : '';
      d.innerHTML = `<span class="k">${esc(k)}</span><label style="display:flex;align-items:center;cursor:pointer;"><input type="checkbox" data-field="${k}" ${checked} style="display:none;"><span class="chk" style="width:14px;height:14px;font-size:11px;border:1px solid var(--bdr);background:var(--bg2);display:flex;align-items:center;justify-content:center;color:var(--or);">${v?'*':''}</span></label>`;
      const chk = d.querySelector('input[type=checkbox]');
      const visual = d.querySelector('.chk');
      chk.addEventListener('change', () => { visual.textContent = chk.checked ? '*' : ''; visual.style.borderColor = chk.checked ? 'var(--or)' : ''; visual.style.background = chk.checked ? 'var(--or-soft)' : ''; });
      fields[k] = () => d.querySelector('input[type=checkbox]').checked ? 1 : 0;
    } else if (cfg.textareas.includes(k)) {
      d.style.flexDirection = 'column'; d.style.alignItems = 'stretch'; d.style.gap = '2px';
      d.innerHTML = `<span class="k">${esc(k)}</span><textarea data-field="${k}">${esc(String(v ?? ''))}</textarea>`;
      fields[k] = () => d.querySelector('textarea').value;
    } else if (cfg.numbers.includes(k)) {
      d.innerHTML = `<span class="k">${esc(k)}</span><input class="s-num" type="number" data-field="${k}" value="${v ?? ''}" style="width:60px;text-align:right;">`;
      fields[k] = () => parseFloat(d.querySelector('input').value);
    } else {
      d.innerHTML = `<span class="k">${esc(k)}</span><input class="s-text" data-field="${k}" value="${esc(String(v ?? ''))}" style="max-width:200px;text-align:right;">`;
      fields[k] = () => d.querySelector('input').value;
    }
    body.appendChild(d);
  });

  // action buttons
  const actions = document.createElement('div');
  actions.className = 'detail-actions';

  const saveBtn = document.createElement('button');
  saveBtn.className = 's-btn btn-gr'; saveBtn.textContent = 'SAVE';
  saveBtn.addEventListener('click', async () => {
    const updates = { id: entityId };
    Object.entries(fields).forEach(([k, getter]) => { updates[k] = getter(); });
    saveBtn.textContent = '...';
    const r = await dbq(cfg.updateType, updates);
    if (r?.success) { setStatus('saved', 'gr'); cfg.reload(); $('#detail-panel').classList.remove('open'); }
    else { setStatus(r?.error || 'save failed', 'rd'); saveBtn.textContent = 'SAVE'; }
  });
  actions.appendChild(saveBtn);

  if (cfg.toggleType) {
    const togBtn = document.createElement('button');
    togBtn.className = 's-btn btn-am'; togBtn.textContent = data.active ? 'DEACTIVATE' : 'ACTIVATE';
    togBtn.addEventListener('click', async () => {
      togBtn.textContent = '...';
      const r = await dbq(cfg.toggleType, { id: entityId });
      if (r?.success) { setStatus('toggled', 'am'); cfg.reload(); $('#detail-panel').classList.remove('open'); }
      else { setStatus(r?.error || 'failed', 'rd'); togBtn.textContent = 'TOGGLE'; }
    });
    actions.appendChild(togBtn);
  }

  if (cfg.deleteType) {
    const delBtn = document.createElement('button');
    delBtn.className = 's-btn btn-rd'; delBtn.textContent = 'DELETE';
    delBtn.addEventListener('click', async () => {
      if (!confirm(`Delete this ${entityType}? This cannot be undone.`)) return;
      delBtn.textContent = '...';
      const r = await dbq(cfg.deleteType, { id: entityId });
      if (r?.success) { setStatus('deleted', 'rd'); cfg.reload(); $('#detail-panel').classList.remove('open'); }
      else { setStatus(r?.error || 'failed', 'rd'); delBtn.textContent = 'DELETE'; }
    });
    actions.appendChild(delBtn);
  }

  body.appendChild(actions);
  $('#detail-panel').classList.add('open');
}

/* ── load facts ── */
async function loadFacts() {
  const r = await dbq('facts', {
    search: $('#fact-search').value.trim(),
    category: $('#fact-cat-filter').value,
    include_inactive: $('#fact-show-inactive').checked,
    limit: 300,
  });
  if (!r || r.error) return;
  const tbody = $('#facts-tbody');
  tbody.innerHTML = '';
  const catColor = { user_pref: 'am', project: 'bl', environment: 'cy', workflow: 'vi', general: '' };
  (r.facts || []).forEach(f => {
    const tr = document.createElement('tr');
    tr.style.opacity = f.active ? '1' : '0.4';
    tr.style.cursor = 'pointer';
    tr.innerHTML = `
      <td style="color:var(--fg3)">${f.id}</td>
      <td><span class="badge b-${catColor[f.category]||'dm'}">${esc(f.category||'')}</span></td>
      <td style="color:var(--cy);font-size:9px">${esc(f.subject_key||'')}</td>
      <td style="color:var(--wh)">${esc(f.content||'')}</td>
      <td style="color:var(--or);text-align:center">${f.importance}</td>
      <td style="text-align:center">${(f.salience||0).toFixed(2)}</td>
      <td style="text-align:center;color:${f.exclusive?'var(--gr)':'var(--fg3)'}">${f.exclusive?'*':''}</td>
      <td style="color:var(--fg2);font-size:9px">${esc(f.updated_at_str||'')}</td>`;
    tr.addEventListener('click', () => showEditableDetail('fact', f.id, {
      id: f.id, content: f.content, category: f.category||'general', topic: f.topic||'',
      subject_key: f.subject_key||'', value_key: f.value_key||'',
      importance: f.importance, confidence: f.confidence||0,
      salience: (f.salience||0).toFixed(2), exclusive: f.exclusive?1:0,
      polarity: f.polarity||'', active: f.active?1:0,
      source: f.source||'', session: f.source_session_id||'',
      created: f.created_at_str||'', updated: f.updated_at_str||'',
    }));
    tbody.appendChild(tr);
  });
}

/* ── load topics ── */
async function loadTopics() {
  const r = await dbq('topics');
  if (!r || r.error) return;
  const tbody = $('#topics-tbody');
  tbody.innerHTML = '';
  (r.topics || []).forEach(t => {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.innerHTML = `
      <td style="color:var(--vi);font-weight:700">${esc(t.title||t.slug)}</td>
      <td><span class="badge b-dm">${esc(t.category||'')}</span></td>
      <td style="color:var(--or);text-align:center">${t.fact_count}</td>
      <td style="font-size:9px">${esc((t.summary||'').substring(0,120))}</td>
      <td style="color:var(--or);text-align:center">${t.importance}</td>
      <td style="text-align:center">${(t.salience||0).toFixed(2)}</td>
      <td style="color:var(--fg2);font-size:9px">${esc(t.updated_at_str||'')}</td>`;
    tr.addEventListener('click', () => showEditableDetail('topic', t.id, {
      id: t.id, slug: t.slug, title: t.title||t.slug, category: t.category||'general',
      facts: t.fact_count, importance: t.importance,
      salience: (t.salience||0).toFixed(2), summary: t.summary||'',
      updated: t.updated_at_str||'',
    }));
    tbody.appendChild(tr);
  });
}

/* ── load sessions ── */
async function loadSessions() {
  const r = await dbq('sessions');
  if (!r || r.error) return;
  const tbody = $('#sessions-tbody');
  tbody.innerHTML = '';
  (r.sessions || []).forEach(s => {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    const sc = s.status === 'open' ? 'gr' : 'fg2';
    tr.innerHTML = `
      <td style="color:var(--cy);font-size:9px">${esc(s.session_id||'')}</td>
      <td><span class="badge b-${sc}">${esc(s.status||'')}</span></td>
      <td style="font-size:9px">${esc((s.summary||'').substring(0,150))}</td>
      <td style="color:var(--fg2);font-size:9px">${esc(s.started_at_str||'')}</td>
      <td style="color:var(--fg2);font-size:9px">${esc(s.last_activity_str||'')}</td>`;
    tr.addEventListener('click', () => showDetail('session', [
      ['id', s.session_id, 'cy'], ['status', s.status, sc], ['label', s.label||''],
      ['summary', s.summary||''], ['started', s.started_at_str||''],
      ['ended', s.ended_at_str||''], ['last_activity', s.last_activity_str||''],
    ]));
    tbody.appendChild(tr);
  });
}

/* ── load prefs + policies ── */
async function loadPrefs() {
  const [pr, po] = await Promise.all([dbq('preferences'), dbq('policies')]);
  const tbody = $('#prefs-tbody');
  tbody.innerHTML = '';
  const render = (items, type) => {
    (items || []).forEach(p => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      const key = p.preference_key || p.policy_key || '';
      const bc = type === 'pref' ? 'b-am' : 'b-vi';
      tr.innerHTML = `
        <td style="font-size:9px"><span class="badge ${bc}">${type}</span> ${esc(key)}</td>
        <td style="color:var(--wh)">${esc(p.label||'')}</td>
        <td style="font-size:9px">${esc((p.content||p.value||'').substring(0,120))}</td>
        <td style="color:var(--or);text-align:center">${p.importance}</td>
        <td style="text-align:center">${(p.salience||0).toFixed(2)}</td>
        <td style="color:var(--fg2);font-size:9px">${esc(p.updated_at_str||'')}</td>`;
      tr.addEventListener('click', () => showEditableDetail(type === 'pref' ? 'preference' : 'policy', p.id, {
        id: p.id, type, key, label: p.label||'',
        value: p.value||'', content: p.content||'',
        importance: p.importance, salience: (p.salience||0).toFixed(2),
        updated: p.updated_at_str||'',
      }));
      tbody.appendChild(tr);
    });
  };
  render(pr?.preferences, 'pref');
  render(po?.policies, 'policy');
}

/* ── load contradictions ── */
async function loadContra() {
  const r = await dbq('contradictions');
  if (!r || r.error) return;
  const tbody = $('#contra-tbody');
  tbody.innerHTML = '';
  (r.contradictions || []).forEach(c => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="color:var(--cy);font-size:9px">${esc(c.subject_key||'')}</td>
      <td><span class="badge b-am">${esc(c.resolution||'')}</span></td>
      <td style="color:var(--gr);font-size:9px">${esc((c.winner_content||'').substring(0,80))}</td>
      <td style="color:var(--rd);font-size:9px;text-decoration:line-through">${esc((c.loser_content||'').substring(0,80))}</td>
      <td style="color:var(--fg2);font-size:9px">${esc(c.created_at_str||'')}</td>`;
    tbody.appendChild(tr);
  });
}

/* ── checkbox visual hack (standalone ones) ── */
$('#fact-show-inactive')?.addEventListener('change', function() {
  const chk = this.parentElement.querySelector('.chk');
  if (chk) { chk.style.borderColor = this.checked ? 'var(--or)' : ''; chk.style.background = this.checked ? 'var(--or-soft)' : ''; chk.textContent = this.checked ? '*' : ''; }
});

/* ── wire buttons ── */
$('#btn-browse').addEventListener('click', async () => { const p = await api.pickHermesHome(); if (p) $('#hermes-path').value = p; });
$('#btn-connect').addEventListener('click', connect);
$('#btn-refresh').addEventListener('click', refreshDash);
$('#btn-load-facts').addEventListener('click', loadFacts);
$('#btn-load-topics').addEventListener('click', loadTopics);
$('#btn-load-sessions').addEventListener('click', loadSessions);
$('#btn-load-prefs').addEventListener('click', loadPrefs);
$('#btn-load-contra').addEventListener('click', loadContra);
$('#detail-close').addEventListener('click', () => $('#detail-panel').classList.remove('open'));
$('#hermes-path').addEventListener('keydown', e => { if (e.key === 'Enter') connect(); });
$('#fact-search').addEventListener('keydown', e => { if (e.key === 'Enter') loadFacts(); });
$$('.save-btn').forEach(b => b.addEventListener('click', saveConfig));
$$('.revert-btn').forEach(b => b.addEventListener('click', revertConfig));

/* shortcut nav buttons */
$('#btn-open-graph').addEventListener('click', () => { document.querySelector('[data-view="v-graph"]').click(); if (typeof loadGraph === 'function') loadGraph(); });
$('#btn-open-wiki').addEventListener('click', () => { document.querySelector('[data-view="v-wiki"]').click(); if (typeof loadWikiNav === 'function') loadWikiNav(); });

/* ── nav toggle ── */
$('#nav-toggle')?.addEventListener('click', () => {
  const nav = $('#nav');
  nav.classList.toggle('expanded');
  const isExpanded = nav.classList.contains('expanded');
  $('#nav-toggle').textContent = isExpanded ? '<' : '>';
  saveApp({ navExpanded: isExpanded });
});
(() => { if (loadApp().navExpanded) { $('#nav')?.classList.add('expanded'); const t = $('#nav-toggle'); if (t) t.textContent = '<'; } })();

/* ── auto-connect ── */
if (hermesHome) setTimeout(connect, 200);
