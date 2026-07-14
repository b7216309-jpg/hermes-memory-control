'use strict';

const assert = require('node:assert/strict');
const { discoverProfiles, runBridge } = require('../src/main/bridge');

async function main() {
  const profiles = await discoverProfiles();
  assert(profiles.length > 0, 'No WSL profile was discovered');
  const preferred = process.env.HMC_WSL_DISTRO;
  const profile = profiles.find((item) => !preferred || item.distro === preferred) || profiles[0];
  const probe = await runBridge(profile, 'probe', {});
  assert.equal(probe.control.protocol, 2);
  assert.equal(probe.memory.installed, true);
  assert.equal(probe.agency.installed, true);
  assert.equal(probe.agency.runtime.contract.source_support, true);
  if (probe.agency.runtime.contract.stored_job.found) {
    assert.equal(probe.agency.runtime.contract.stored_job.prompt_matches_config, true);
  }
  const database = probe.memory.databases.find((item) => item.exists)?.id;
  assert(database, 'No memory database exists');
  const overview = await runBridge(profile, 'memory_overview', { database });
  assert.equal(overview.doctor.integrity[0], 'ok');
  for (const candidate of probe.memory.databases.filter((item) => item.exists)) {
    const report = await runBridge(profile, 'memory_overview', { database: candidate.id });
    assert.equal(report.doctor.integrity[0], 'ok', `Integrity failed for ${candidate.id}`);
  }
  for (const table of ['facts','topics','episodes','sessions','traces','journals','summaries','preferences','policies','contradictions','history','links','evidence','working','procedures','prospective','autobiographical','associations','approvals','pending']) {
    const result = await runBridge(profile, 'memory_list', { database, table, limit: 2 });
    assert.equal(result.table, table);
    assert(Array.isArray(result.rows));
  }
  const graph = await runBridge(profile, 'memory_graph', { database, limit: 50 });
  assert(Array.isArray(graph.nodes));
  assert(Array.isArray(graph.edges));
  const agency = await runBridge(profile, 'agency_snapshot', {});
  assert(agency.snapshot.runtime);
  for (const table of ['intentions','reflections','decisions','events','meta']) {
    const result = await runBridge(profile, 'agency_list', { table, limit: 2 });
    assert.equal(result.table, table);
  }
  const schema = await runBridge(profile, 'config_schema', {});
  assert(schema.memory.length > 20);
  assert(schema.agency.length > 10);
  await runBridge(profile, 'wiki_list', {});
  if (process.env.HMC_MUTATION_SMOKE === '1') {
    await runBridge(profile, 'memory_backup', { database }, { mutation: true });
    await runBridge(profile, 'agency_backup', {}, { mutation: true });
    const audit = await runBridge(profile, 'audit_list', { limit: 10 });
    assert.equal(audit.valid, true);
    assert(audit.events.some((item) => item.operation === 'memory_backup'));
    assert(audit.events.some((item) => item.operation === 'agency_backup'));
  }
  process.stdout.write(JSON.stringify({ ok: true, profile, memoryDatabase: database, memoryDoctor: overview.doctor.ok, agencyEligible: agency.gates.eligible }, null, 2) + '\n');
}

main().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
