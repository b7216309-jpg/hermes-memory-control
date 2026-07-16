'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { buildPlan, cleanPayload, isLabAction, READ_ACTIONS } = require('../src/main/plans');
const { cleanWslText, run, runBridge } = require('../src/main/bridge');

test('read surface is finite and contains no arbitrary command or SQL operation', () => {
  assert(READ_ACTIONS.has('memory_list'));
  assert(READ_ACTIONS.has('agency_snapshot'));
  assert(!READ_ACTIONS.has('sql'));
  assert(!READ_ACTIONS.has('shell'));
  assert(!READ_ACTIONS.has('read_file'));
});

test('payload cleaner clones ordinary data into null-prototype objects', () => {
  const cleaned = cleanPayload({ id: 4, nested: { label: 'safe' }, values: [true, 2] });
  assert.equal(Object.getPrototypeOf(cleaned), null);
  assert.equal(Object.getPrototypeOf(cleaned.nested), null);
  assert.deepEqual({ ...cleaned.nested }, { label: 'safe' });
});

test('payload cleaner rejects prototype keys, NUL bytes, deep trees, and non-finite values', () => {
  assert.throws(() => cleanPayload(JSON.parse('{"__proto__":{"polluted":true}}')), /invalid key/);
  assert.throws(() => cleanPayload({ value: 'a\0b' }), /safety limits/);
  assert.throws(() => cleanPayload({ a: { b: { c: 1 } } }, { maxDepth: 1 }), /deeply nested/);
  assert.throws(() => cleanPayload({ value: Infinity }), /non-finite/);
});

test('plans are one of the explicit mutation contracts', () => {
  const plan = buildPlan('memory_backup', { database: 'base' });
  assert.match(plan.id, /^[0-9a-f-]{36}$/);
  assert.equal(plan.phrase, 'CREATE BACKUP');
  assert.equal(buildPlan('memory_update_item', { table: 'facts', id: 1 }).phrase, 'UPDATE MEMORY');
  assert.throws(() => buildPlan('arbitrary_shell', {}), /Unsupported mutation/);
  assert.throws(
    () => buildPlan('gateway_restart', { hidden: 'data' }),
    /Unsupported payload field/,
  );
});

test('educational controls require the lab boundary', () => {
  assert.equal(isLabAction('lab_apply_profile', {}), true);
  assert.equal(isLabAction('memory_export', { include_sensitive: true }), true);
  assert.equal(isLabAction('config_apply', { changes: { allow_credential_memory: true } }), true);
  assert.equal(isLabAction('config_apply', { changes: { educational_allow_heartbeat_tools: true } }), true);
  assert.equal(isLabAction('config_apply', { changes: { educational_subjective_mode: 'cold' } }), true);
  assert.equal(isLabAction('config_apply', { changes: { prefetch_limit: 8 } }), false);
  assert.throws(() => isLabAction('memory_export', { include_sensitive: 'false' }), /must be boolean/);
  assert.throws(
    () => buildPlan('memory_resolve_approval', { id: 1, approved: 'false' }),
    /must be boolean/,
  );
});

test('WSL output normalizer handles UTF-16-like NUL padding', () => {
  assert.equal(cleanWslText('U\0b\0u\0n\0t\0u\0\r\0\n\0'), 'Ubuntu');
});

test('bridge mutation mode rejects truthy strings before launching WSL', async () => {
  await assert.rejects(
    runBridge({ distro: 'Ubuntu', home: '/home/test/.hermes' }, 'probe', {}, { mutation: 'false' }),
    /mutation must be boolean/,
  );
});

test('process bridge settles once when output exceeds its bound', async () => {
  await assert.rejects(
    run(process.execPath, ['-e', 'process.stdout.write("overflow")'], { maxOutput: 3 }),
    /output exceeded the safety limit/,
  );
});

test('process bridge enforces its timeout without a later close race', async () => {
  await assert.rejects(
    run(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { timeout: 20 }),
    /timed out/,
  );
});

test('process bridge returns stdout and reports child stderr', async () => {
  assert.equal(await run(process.execPath, ['-e', 'process.stdout.write("ok")']), 'ok');
  await assert.rejects(
    run(process.execPath, ['-e', 'process.stderr.write("nope"); process.exit(4)']),
    /nope/,
  );
});
