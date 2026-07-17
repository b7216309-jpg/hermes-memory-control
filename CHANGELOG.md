# Changelog

## 3.2.0 — 2026-07-17

- Updated the suite contract for Memory 3.6 and Conscious Agency 1.2 real-conversation heartbeat
  execution.
- Replaced retired disposable-session audits with checks for real-session execution, hidden-trigger
  persistence suppression, transcript reconciliation, exact assistant commit, single delivery
  ownership, and ordered inbound-user handoff.
- Added Memory assistant-provenance auditing so heartbeat output can enter the real Memory session
  without being classified as a user statement.
- Updated anonymous demo data, UI versioning, documentation, and regression coverage for the new
  integration contract.

## 3.1.0 — 2026-07-17

- Added complete Memory 3.5 and Conscious Agency 1.1 contract coverage, including disposable
  session cleanup, stale-session reconciliation, claimed-wake recovery, the runner process lease,
  decision-delivery outcomes, and heartbeat-to-Memory isolation.
- Audited the heartbeat's adapter-free model-work route and rejected the reserved Hermes
  `gateway_session_id` pin that can silently drop or misroute a synthetic turn.
- Made all database browsing use the plugins' read-only store modes so connecting or inspecting
  cannot migrate or modify encrypted state.
- Made database edits transactional with history, FTS, topic, and reference repair in the same
  commit.
- Added manifest-bound encrypted backups, retention, digest verification, rollback-protected
  restores, and combined restore/restart failure diagnostics.
- Bound each confirmation token to the exact payload, current config/database/WAL state, Control
  bridge implementation, and installed Memory/Agency implementation files; undeclared payload
  fields are rejected in both Electron and the WSL bridge.
- Added a cross-process mutation lease so two Control Center instances cannot mutate the suite at
  the same time.
- Hardened the append-only audit with cross-process locking and text hashing, and expanded WSL,
  Electron, renderer, privacy, rollback, and concurrency tests.
- Removed every retired heartbeat iteration control while preserving an uncapped model/tool path
  and the independent 600-second wall-clock timeout.

## 3.0.0 — 2026-07-16

- Replaced every obsolete Agency-cron action with native heartbeat status, manual wake,
  enable/disable, exact legacy migration, and gateway-integration audit.
- Updated Educational Lab and recommended profiles for Conscious Agency 1.0 heartbeat controls.
- Removed cron prompt hashing/refresh/rollback logic; Agency configuration now activates by one
  rollback-protected gateway restart while unrelated Hermes cron jobs remain untouched.
- Added UI status for heartbeat interval, target, last outcome, reason, and durable run count.
- Exposed Agency's heartbeat-only tool-iteration boundary in the generated configuration editor
  while leaving model output length uncapped and keeping the 10-minute timeout independent.
- Updated synthetic demo data, security plans, bridge regression tests, and full documentation for
  Memory 3.4 and Conscious Agency 1.0.

## 2.4.0 — 2026-07-16

- Added compatibility for Consolidating Local Memory 3.4.0 and Conscious Agency 0.6.0.
- Added an `educational_expressive` contract classification for the four-on, tool-off Agency shape.
- Audited provider-boundary cron tool isolation from installed runtime source and effective config,
  rather than assuming every boundary must appear as prose in the stored cron prompt.
- Updated synthetic demo data to subjective protocol 2.8 and removed obsolete contract markers.
- Kept the renderer sandbox, allowlisted bridge, rollback-protected mutations, SQLCipher handling,
  anonymous screenshots, and hash-chained audit contract unchanged.

## 2.3.2 — 2026-07-16

- Supported Conscious Agency 0.5.1 and protocol 1.4 journal chains.
- Removed obsolete pre-0.5 control-signal handling.
