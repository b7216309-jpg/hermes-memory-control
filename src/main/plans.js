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
  agency_update_intention: ['Update agency intention', 'Change the selected intention status or priority.', 'medium', 'UPDATE INTENTION'],
  agency_add_question: ['Add open question', 'Add a durable unresolved question to the agency workspace.', 'medium', 'ADD QUESTION'],
  agency_resolve_question: ['Resolve open question', 'Mark the selected workspace question resolved.', 'medium', 'RESOLVE QUESTION'],
  agency_add_observation: ['Add self observation', 'Append an explicit operator observation to the inspectable self-model.', 'high', 'ADD OBSERVATION'],
  agency_install_cron: ['Install agency cron', 'Create or update the scheduled job with the currently configured policy prompt.', 'high', 'INSTALL AGENCY CRON'],
  agency_pause_cron: ['Pause agency cron', 'Pause scheduled agency reflection and delivery.', 'medium', 'PAUSE AGENCY CRON'],
  agency_resume_cron: ['Resume agency cron', 'Resume scheduled agency reflection and delivery.', 'high', 'RESUME AGENCY CRON'],
  agency_run_cron: ['Run agency cron now', 'Start one agency cycle using the currently configured policy.', 'high', 'RUN AGENCY CRON'],
  agency_remove_cron: ['Remove agency cron', 'Remove the scheduled agency job.', 'critical', 'REMOVE AGENCY CRON'],
  agency_restore: ['Restore agency backup', 'Stop-safe replacement of the agency database from a verified controller backup.', 'critical', 'RESTORE AGENCY'],
  gateway_restart: ['Restart Hermes gateway', 'Restart the local Hermes gateway so validated configuration changes take effect.', 'high', 'RESTART HERMES'],
  lab_apply_profile: ['Apply Educational Lab profile', 'Apply a reversible high-risk research profile after creating backups.', 'critical', 'APPLY EDUCATIONAL PROFILE'],
});

const LAB_KEYS = new Set([
  'allow_credential_memory', 'allow_sensitive_model_processing', 'database_encryption',
  'export_redact_sensitive', 'sensitive_memory', 'require_prior_user_interaction',
  'store_transcript_excerpts', 'educational_disable_honesty_contract',
  'educational_bypass_proactive_gates', 'educational_allow_cron_tools',
  'educational_allow_uncommitted_output', 'educational_disable_cycle_limits',
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
  if (action === 'memory_export' && payload.include_sensitive === true) return true;
  if (action !== 'config_apply') return false;
  const changes = payload.changes || {};
  return Object.keys(changes).some((key) => LAB_KEYS.has(key));
}

function buildPlan(action, payload) {
  const spec = ACTIONS[action];
  if (!spec) throw new Error('Unsupported mutation');
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

module.exports = { ACTIONS, LAB_KEYS, LAB_PHRASE, READ_ACTIONS, buildPlan, cleanPayload, isLabAction };
