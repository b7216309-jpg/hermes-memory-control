'use strict';

const crypto = require('node:crypto');

const LAB_PHRASE = 'I UNDERSTAND THIS IS AN EDUCATIONAL LAB';
const READ_ACTIONS = new Set([
  'probe', 'memory_overview', 'memory_list', 'memory_search', 'memory_graph',
  'agency_snapshot', 'agency_list', 'audit_list', 'backups_list', 'config_schema',
  'wiki_list', 'wiki_read',
]);

const ACTIONS = Object.freeze({
  memory_backup: ['Create memory backup', 'Create and verify an encrypted-compatible point-in-time backup.', 'low', 'CREATE BACKUP'],
  memory_export: ['Export memory', 'Write a portable, sensitive-redacted JSON export.', 'medium', 'EXPORT MEMORY'],
  memory_deactivate_fact: ['Deactivate memory fact', 'Soft-deactivate the selected fact and preserve its history.', 'medium', 'DEACTIVATE FACT'],
  memory_update_item: ['Update memory item', 'Apply an allowlisted schema-aware edit after a verified database backup.', 'high', 'UPDATE MEMORY'],
  memory_resolve_approval: ['Resolve memory approval', 'Apply the selected approve/deny decision.', 'medium', 'RESOLVE APPROVAL'],
  memory_resolve_intention: ['Resolve prospective memory', 'Change the selected prospective-memory status.', 'medium', 'RESOLVE INTENTION'],
  memory_retry_failed: ['Retry failed memory work', 'Requeue failed durable work; a partially completed operation may repeat.', 'high', 'RETRY FAILED WORK'],
  memory_maintain: ['Run memory maintenance', 'Apply retention and size budgets and vacuum when appropriate.', 'high', 'MAINTAIN MEMORY'],
  memory_restore: ['Restore memory backup', 'Stop-safe replacement of the active memory database from a verified controller backup.', 'critical', 'RESTORE MEMORY'],
  config_apply: ['Apply plugin configuration', 'Validate, atomically save, and audit the staged plugin configuration changes.', 'high', 'APPLY CONFIG'],
  agency_backup: ['Create agency backup', 'Create and verify an encrypted-compatible point-in-time agency backup.', 'low', 'CREATE AGENCY BACKUP'],
  agency_pause: ['Pause agency', 'Pause agency behavior with the supplied operator reason.', 'medium', 'PAUSE AGENCY'],
  agency_resume: ['Resume agency', 'Resume operator-paused agency behavior.', 'high', 'RESUME AGENCY'],
  agency_focus: ['Change agency focus', 'Replace the persistent global focus and record the reason.', 'medium', 'CHANGE FOCUS'],
  agency_add_intention: ['Add agency intention', 'Create a durable operator intention.', 'medium', 'ADD INTENTION'],
  agency_update_intention: ['Update agency intention', 'Change the selected intention status, priority, or ISO-8601 deadline.', 'medium', 'UPDATE INTENTION'],
  agency_add_question: ['Add open question', 'Add a durable unresolved question to the agency workspace.', 'medium', 'ADD QUESTION'],
  agency_resolve_question: ['Resolve open question', 'Mark the selected workspace question resolved.', 'medium', 'RESOLVE QUESTION'],
  agency_add_observation: ['Add self observation', 'Append an explicit operator observation to the inspectable self-model.', 'high', 'ADD OBSERVATION'],
  agency_heartbeat_run: ['Wake agency heartbeat', 'Queue one gateway-native heartbeat in the latest external Hermes conversation.', 'medium', 'WAKE AGENCY HEARTBEAT'],
  agency_heartbeat_enable: ['Enable agency heartbeat', 'Enable the native scheduler and restart Hermes if it is currently running.', 'high', 'ENABLE AGENCY HEARTBEAT'],
  agency_heartbeat_disable: ['Disable agency heartbeat', 'Disable the native scheduler and restart Hermes if it is currently running.', 'medium', 'DISABLE AGENCY HEARTBEAT'],
  agency_migrate_heartbeat: ['Remove legacy agency cron', 'Back up Agency state and remove only the obsolete cron job recorded by the plugin.', 'critical', 'REMOVE LEGACY AGENCY CRON'],
  agency_restore: ['Restore agency backup', 'Stop-safe replacement of the agency database from a verified controller backup.', 'critical', 'RESTORE AGENCY'],
  gateway_restart: ['Restart Hermes gateway', 'Restart the local Hermes gateway so validated configuration changes take effect.', 'high', 'RESTART HERMES'],
  lab_apply_profile: ['Apply Educational Lab profile', 'Apply a reversible high-risk research profile after creating backups.', 'critical', 'APPLY EDUCATIONAL PROFILE'],
});

const ACTION_PAYLOAD_FIELDS = Object.freeze({
  memory_backup: ['database'],
  memory_export: ['database', 'include_sensitive'],
  memory_deactivate_fact: ['database', 'id'],
  memory_update_item: ['database', 'table', 'id', 'changes'],
  memory_resolve_approval: ['database', 'id', 'approved', 'resolution'],
  memory_resolve_intention: ['database', 'id', 'status'],
  memory_retry_failed: ['database', 'limit'],
  memory_maintain: ['database'],
  memory_restore: ['database', 'backup_id'],
  config_apply: ['plugin', 'changes'],
  agency_backup: [],
  agency_pause: ['reason'],
  agency_resume: [],
  agency_focus: ['focus', 'reason'],
  agency_add_intention: ['title', 'rationale', 'priority', 'autonomy', 'due_at'],
  agency_update_intention: ['id', 'status', 'priority', 'due_at'],
  agency_add_question: ['question'],
  agency_resolve_question: ['id'],
  agency_add_observation: ['observation'],
  agency_heartbeat_run: [],
  agency_heartbeat_enable: [],
  agency_heartbeat_disable: [],
  agency_migrate_heartbeat: [],
  agency_restore: ['backup_id'],
  gateway_restart: [],
  lab_apply_profile: ['profile'],
});

const LAB_KEYS = new Set([
  'allow_credential_memory', 'allow_sensitive_model_processing', 'database_encryption',
  'export_redact_sensitive', 'sensitive_memory', 'require_prior_user_interaction',
  'store_transcript_excerpts', 'educational_disable_honesty_contract',
  'educational_bypass_proactive_gates', 'educational_allow_heartbeat_tools',
  'educational_allow_uncommitted_output', 'educational_disable_cycle_limits',
  'educational_subjective_mode',
]);

function cleanPayload(value, options = {}, depth = 0) {
  const { maxDepth = 6, maxKeys = 100, maxString = 20_000 } = options;
  if (depth > maxDepth) throw new Error('Request payload is too deeply nested');
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('Request contains a non-finite number');
    return value;
  }
  if (typeof value === 'string') {
    if (value.length > maxString || value.includes('\0')) throw new Error('Request string exceeds safety limits');
    return value;
  }
  if (Array.isArray(value)) {
    if (value.length > maxKeys) throw new Error('Request array exceeds safety limits');
    return value.map((item) => cleanPayload(item, options, depth + 1));
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value);
    if (entries.length > maxKeys) throw new Error('Request object exceeds safety limits');
    const result = Object.create(null);
    for (const [key, item] of entries) {
      if (!/^[\w.-]{1,80}$/.test(key) || ['__proto__', 'prototype', 'constructor'].includes(key)) {
        throw new Error('Request contains an invalid key');
      }
      result[key] = cleanPayload(item, options, depth + 1);
    }
    return result;
  }
  throw new Error('Request contains an unsupported value');
}

function isLabAction(action, payload = {}) {
  if (action === 'lab_apply_profile') return true;
  if (action === 'memory_export') {
    if ('include_sensitive' in payload && typeof payload.include_sensitive !== 'boolean') {
      throw new Error('include_sensitive must be boolean');
    }
    if (payload.include_sensitive === true) return true;
  }
  if (action !== 'config_apply') return false;
  const changes = payload.changes || {};
  return Object.keys(changes).some((key) => LAB_KEYS.has(key));
}

function validateMutationPayload(action, payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('Mutation payload must be an object');
  }
  if (action === 'memory_resolve_approval' && typeof payload.approved !== 'boolean') {
    throw new Error('approved must be boolean');
  }
  if (action === 'memory_export' && 'include_sensitive' in payload && typeof payload.include_sensitive !== 'boolean') {
    throw new Error('include_sensitive must be boolean');
  }
  const allowed = new Set(ACTION_PAYLOAD_FIELDS[action] || []);
  const unexpected = Object.keys(payload).filter((key) => !allowed.has(key)).sort();
  if (unexpected.length) {
    throw new Error(`Unsupported payload field for ${action}: ${unexpected.join(', ')}`);
  }
}

function buildPlan(action, payload) {
  const spec = ACTIONS[action];
  if (!spec) throw new Error('Unsupported mutation');
  validateMutationPayload(action, payload);
  return {
    id: crypto.randomUUID(),
    action,
    payload,
    title: spec[0],
    summary: spec[1],
    risk: spec[2],
    phrase: spec[3],
  };
}

module.exports = {
  ACTIONS,
  ACTION_PAYLOAD_FIELDS,
  LAB_KEYS,
  LAB_PHRASE,
  READ_ACTIONS,
  buildPlan,
  cleanPayload,
  isLabAction,
  validateMutationPayload,
};
