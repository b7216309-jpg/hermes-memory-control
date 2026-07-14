# Security model

Hermes Control Center is a local operator tool with authority over sensitive agent state. Its main
security objective is to prevent untrusted renderer content, accidental clicks and malformed IPC
payloads from becoming arbitrary code execution or silent state corruption.

## Trust boundaries

- The Windows OS user and the WSL user are trusted operators. Anyone who can replace the app,
  plugin source, Hermes config, `.env`, databases and audit file already controls the system.
- Memory content, wiki Markdown, database rows and plugin output are untrusted data.
- The Electron renderer is untrusted and has no Node integration.
- The Electron main process validates profiles, read operations, mutation plans and Lab sessions.
- The WSL bridge is the final authorization and validation boundary.

## Invariants

1. The renderer never receives environment-secret values.
2. Renderer requests cannot supply a command, SQL statement or filesystem path.
3. WSL processes are spawned with argument arrays and `shell: false`.
4. A mutation requires an explicit allowlisted operation, a fresh single-use plan and an exact
   phrase.
5. Lab operations also require a 15-minute main-process unlock.
6. A database mutation creates and verifies a backup first.
7. Restores accept only an opaque backup ID rooted under the controller backup directory.
8. Configuration is plugin-validated, backed up, written to a same-directory temporary file,
   flushed and atomically replaced.
9. Wiki HTML is sanitized and links are made inert before insertion into the DOM.
10. Encryption mode cannot be toggled as a YAML-only change.

Audit records hash sensitive text fields instead of duplicating memory, prompts, observations or
messages. Failed mutation attempts are recorded too when the audit directory remains available.

## Audit-chain limits

`audit.jsonl` is a SHA-256 hash chain. It detects edits, deletion or reordering inside the chain
when the remaining file is verified. It is not remote attestation: a trusted OS user can replace the
entire application and audit file together. For stronger assurance, periodically copy audit hashes
or backups to a separately controlled, append-only destination.

## Educational Lab

The Lab is hidden to reduce accidental discovery, but hiding is not authorization. The main
process independently enforces its unlock phrase and expiry. Lab operations still use backups,
confirmation phrases, validation and audit.

The controller never patches plugin source. Conscious Agency 0.2 exposes strict default-off Lab
settings for claim-contract, gate, tool-isolation, mutation-limit and output-filter research. The
controller compares those settings with the prompt actually stored in Hermes cron, then refreshes
the job and restarts a running gateway with rollback protection. These overrides affect only the
plugin; Hermes, provider, platform and OS permissions remain outside the controller's authority.

## Reporting

Do not open a public issue containing memory content, configuration secrets, `.env` values,
database files or audit payloads. Reproduce with synthetic data, state the controller/plugin/Hermes
versions, and include only redacted error text.
