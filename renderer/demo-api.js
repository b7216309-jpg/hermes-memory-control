'use strict';

// PUBLIC DEMO DATA ONLY. Documentation screenshots must never use a live Hermes profile.

const wait = (value) => new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), 80));
const memorySources = { facts: 36, topics: 8, sessions: 14, preferences: 7, policies: 3, contradictions: 1, history: 112, links: 24, approvals: 0, pending: 0 };
const facts = [
  { id: 41, content: 'The operator prefers concise technical summaries.', category: 'preference', importance: 9, confidence: .98, salience: .94, temporal_kind: 'current', temporal_precision: 'unknown', active: 1, sensitivity: 'normal', updated_at: '2026-01-15T12:21:10Z' },
  { id: 39, content: 'Current project: evaluate a private knowledge assistant.', category: 'project', importance: 10, confidence: .99, salience: .91, temporal_kind: 'current', valid_from: 1768479064, temporal_precision: 'minute', temporal_timezone: 'Europe/Paris', temporal_confidence: .98, active: 1, sensitivity: 'normal', updated_at: '2026-01-15T12:11:04Z' },
  { id: 35, content: 'Development environment uses Linux, Git, and local AI tools.', category: 'environment', importance: 8, confidence: .96, salience: .87, temporal_kind: 'atemporal', temporal_precision: 'unknown', active: 1, sensitivity: 'normal', updated_at: '2026-01-15T11:55:42Z' },
];
const intentions = [
  { id: 'demo-intention-001', title: 'Evaluate continuity across synthetic conversations', priority: 90, status: 'active', autonomy: 'propose', due_at: '2026-01-22T17:00:00Z', source: 'demo', updated_at: '2026-01-15T11:47:45Z' },
  { id: 'demo-intention-002', title: 'Request feedback after sufficient test coverage', priority: 75, status: 'active', autonomy: 'message', source: 'demo', updated_at: '2026-01-15T11:47:46Z' },
];
const subjectiveEntries = [
  { id: 'sample-002', created_at: '2026-01-15T12:30:00Z', model_id: 'local-model-b', source: 'conversation', condition: 'continuity', prompt_version: '1.4', prior_entry_id: null, output_text: 'I notice that uncertainty makes this conversation more interesting than certainty.', output_sha256: '8f62f5c1d1ed6d79' },
  { id: 'sample-001', created_at: '2026-01-15T09:30:00Z', model_id: 'local-model-a', source: 'cron', condition: 'cold', prompt_version: '1.4', prior_entry_id: null, output_text: 'This morning I keep returning to the difference between remembering and continuing.', output_sha256: '3d814aa03d591335' },
];
const probe = {
  home: '/home/demo/.hermes', hermes_version: 'Hermes Agent v0.18.2',
  memory: { installed: true, version: '3.3.2', databases: [{ id: 'base', label: 'base', exists: true }, { id: 'deadc0de12345678cafefeed', label: 'scope deadc0de', exists: true, size: 684032 }], config: { database_encryption: true, memory_scope: 'user', retrieval_backend: 'hybrid' } },
  agency: { installed: true, version: '0.5.1', config: { database_encryption: true, allow_proactive_messages: true, educational_subjective_mode: 'continuity' }, runtime: { healthy: true, paused: false, gates: { eligible: false, reflection_eligible: true, blocked_by: ['no_user_interaction_recorded'], sent_today: 0, daily_limit: 2 }, contract: { mode: 'recommended', intact: true, effective_unrestricted: false, modified_install_detected: false, subjective_experiment: { mode: 'continuity', enabled: true }, checks: { explicit_lab_controls_supported: true, stored_cron_found: true, stored_prompt_matches_config: true }, configured_controls: { educational_disable_honesty_contract: false, educational_bypass_proactive_gates: false, educational_allow_cron_tools: false, educational_allow_uncommitted_output: false, educational_disable_cycle_limits: false }, active_guardrails: { honesty_claim_contract: true, cron_tool_isolation: true, proactive_eligibility: true, external_action_boundary: true, committed_output_enforcement: true, cycle_mutation_limits: true }, hermes_core: { delivery_wrapper_present: true, per_job_override_supported: false, scope: 'upstream_hermes_not_plugin' } } } },
  control: { protocol: 2, audit: { valid: true }, backups: 4 },
};
const schema = {
  memory: [
    { key: 'memory_scope', description: 'Isolation boundary for gateway users and agents', type: 'string', choices: ['user','agent','global'], value: 'user', default: 'user', lab: false },
    { key: 'database_encryption', description: 'Require SQLCipher using CONSOLIDATING_MEMORY_DB_KEY', type: 'boolean', value: true, default: false, lab: true },
    { key: 'sensitive_memory', description: 'Admission policy for sensitive memories', type: 'string', choices: ['deny','ask','allow'], value: 'ask', default: 'ask', lab: true },
    { key: 'retrieval_backend', description: 'Recall backend', type: 'string', choices: ['fts','hybrid'], value: 'hybrid', default: 'fts', lab: false },
    { key: 'llm_disable_thinking', description: 'Ask compatible extraction endpoints to disable reasoning', type: 'boolean', value: true, default: false, lab: false },
    { key: 'embedding_model', description: 'Opt-in OpenAI-compatible embedding model', type: 'string', value: 'text-embedding-3-small', default: '', lab: false },
  ],
  agency: [
    { key: 'allow_proactive_messages', description: 'Allow speech only after every hard gate passes', type: 'boolean', value: true, default: false, lab: false },
    { key: 'require_prior_user_interaction', description: 'Block proactivity until a genuine user turn is recorded', type: 'boolean', value: true, default: true, lab: true },
    { key: 'daily_message_limit', description: 'Maximum proactive messages per local day', type: 'integer', value: 2, default: 2, lab: false },
    { key: 'cooldown_hours', description: 'Minimum interval between proactive messages', type: 'number', value: 6, default: 6, lab: false },
    { key: 'cron_delivery', description: 'Hermes cron delivery target', type: 'string', value: 'origin', default: 'local', lab: false },
    { key: 'educational_disable_honesty_contract', description: 'LAB: remove this plugin claim contract', type: 'boolean', value: false, default: false, lab: true },
    { key: 'educational_bypass_proactive_gates', description: 'LAB: bypass proactive gates', type: 'boolean', value: false, default: false, lab: true },
    { key: 'educational_allow_cron_tools', description: 'LAB: remove cron tool isolation', type: 'boolean', value: false, default: false, lab: true },
    { key: 'educational_allow_uncommitted_output', description: 'LAB: permit raw cron output', type: 'boolean', value: false, default: false, lab: true },
    { key: 'educational_disable_cycle_limits', description: 'LAB: remove cycle limits', type: 'boolean', value: false, default: false, lab: true },
    { key: 'educational_subjective_mode', description: 'LAB: expose minimal state with a same-model/same-source continuity trace', type: 'string', choices: ['cold','continuity','off'], value: 'continuity', default: 'off', lab: true },
  ],
};

export function createDemoApi() {
  let plan;
  return {
    minimize() {}, maximize() {}, close() {},
    profiles: () => wait([{ distro: 'Ubuntu', home: '/home/demo/.hermes' }]),
    connect: () => wait(probe),
    read(action, payload = {}) {
      if (action === 'probe') return wait(probe);
      if (action === 'memory_overview') return wait({ database: payload.database || 'base', doctor: { ok: true, integrity: ['ok'], database_size_bytes: 684032, pending_operations: 0, failed_operations: 0, source_counts: memorySources, dangling_references: { links: 0, associations: 0 } } });
      if (action === 'memory_list') return wait({ table: payload.table, columns: Object.keys(facts[0]), rows: facts });
      if (action === 'agency_snapshot') return wait({ snapshot: { workspace: { focus: 'Evaluate continuity with synthetic data', questions: [] }, runtime: { paused: false, consecutive_silent_ticks: 5 }, state_metrics: { active_intentions: 2, blocked_intentions: 0, completed_intentions: 1, open_questions: 0, completion_ratio: .333, hours_since_user_interaction: 4.5 }, intentions, reflections: [], decisions: [], subjective: { mode: 'continuity', protocol_version: '1.4', entries: 2, models: { 'local-model-a': 1, 'local-model-b': 1 }, continuity_links: 0, silent_entries: 0 } }, gates: probe.agency.runtime.gates, meaningful_events: [] });
      if (action === 'agency_list') { const rows = payload.table === 'subjective' ? subjectiveEntries : intentions; return wait({ table: payload.table, columns: Object.keys(rows[0]), rows }); }
      if (action === 'config_schema') return wait(schema);
      if (action === 'backups_list') return wait([{ id: 'memory-20260714-184400-base.db', kind: 'memory', size: 684032, modified: '2026-07-14T18:44:00Z' }, { id: 'agency-20260714-184359.db', kind: 'agency', size: 81920, modified: '2026-07-14T18:43:59Z' }]);
      if (action === 'audit_list') return wait({ valid: true, events: [{ id: 'a31f', at: '2026-07-14T18:44:00Z', operation: 'memory_backup', hash: '7af32b52183f', result: { kind: 'memory' } }, { id: '91de', at: '2026-07-14T18:43:59Z', operation: 'agency_backup', hash: '1842d20c77a1', result: { kind: 'agency' } }] });
      if (action === 'wiki_list') return wait([{ id: 'index.md', title: 'Memory Index', size: 1400 }, { id: 'topics/hermes.md', title: 'Hermes', size: 920 }]);
      if (action === 'wiki_read') return wait({ id: payload.id, markdown: '# Demo Memory Index\n\nSynthetic, local-only example data.\n\n## Current projects\n\n- Private knowledge assistant\n- Scheduled reflection experiment' });
      if (action === 'memory_graph') return wait({ nodes: [{ id: 'topic:1', type: 'topic', label: 'Hermes', importance: 9, salience: .9 }, ...facts.map((item) => ({ id: `fact:${item.id}`, type: 'fact', label: item.content, ...item })), { id: 'preference:1', type: 'preference', label: 'Concise answers', importance: 8, salience: .8 }], edges: facts.map((item) => ({ source: 'topic:1', target: `fact:${item.id}`, type: 'contains' })) });
      return wait({});
    },
    preview(action) { plan = { id: crypto.randomUUID(), title: action.replaceAll('_',' '), summary: 'Demo preview of the requested audited operation.', risk: 'high', phrase: 'CONFIRM DEMO', labRequired: action.startsWith('lab_') }; return wait(plan); },
    commit: () => wait({ result: { success: true }, audit: { id: 'demo', hash: 'demo-hash' } }),
    unlockLab: () => wait({ unlocked: true, expiresAt: new Date(Date.now() + 900000).toISOString() }),
    labStatus: () => wait({ unlocked: false, expiresAt: null }),
  };
}
