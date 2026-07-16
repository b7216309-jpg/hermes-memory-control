# Changelog

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
