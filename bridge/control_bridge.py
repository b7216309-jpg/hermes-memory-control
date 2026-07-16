#!/usr/bin/env python3
"""Narrow WSL-side control plane for Hermes Memory Control.

The Electron renderer cannot send SQL, commands, filesystem paths, or environment
variables. It can only select operations and opaque IDs implemented here.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import hmac
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROTOCOL = 2
MAX_LIMIT = 500
AUTOMATIC_BACKUPS_PER_TARGET = 30
CONFIG_BACKUP_RETENTION = 50
MEMORY_KEY = "consolidating-local-memory"
AGENCY_KEY = "conscious-agency"
SECRET_MARKERS = ("api_key", "secret", "password", "token", "database_key")
AUDIT_TEXT_FIELDS = {
    "content",
    "summary",
    "insight",
    "message",
    "observation",
    "question",
    "focus",
    "rationale",
    "resolution",
    "reason",
    "label",
    "title",
    "value",
    "markdown",
    "candidate_json",
    "payload_json",
    "metadata_json",
    "steps_json",
    "prerequisites_json",
    "error",
}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SCOPE_ID = re.compile(r"^[a-f0-9]{8,64}$")
_AUDIT_THREAD_LOCK = threading.Lock()
_MUTATION_THREAD_LOCK = threading.Lock()

MEMORY_TABLES = {
    "facts": "facts",
    "topics": "topics",
    "episodes": "episodes",
    "sessions": "memory_sessions",
    "traces": "memory_traces",
    "journals": "memory_journals",
    "summaries": "memory_summaries",
    "preferences": "memory_preferences",
    "policies": "memory_policies",
    "contradictions": "contradictions",
    "history": "memory_history",
    "links": "memory_links",
    "evidence": "belief_evidence",
    "working": "working_memory",
    "procedures": "memory_procedures",
    "prospective": "prospective_memories",
    "autobiographical": "autobiographical_events",
    "associations": "memory_associations",
    "approvals": "memory_approvals",
    "pending": "pending_operations",
}
AGENCY_TABLES = {
    "events": "events",
    "intentions": "intentions",
    "reflections": "reflections",
    "decisions": "decisions",
    "subjective": "subjective_entries",
    "meta": "meta",
}
MUTATION_OPERATIONS = {
    "memory_backup",
    "memory_export",
    "memory_deactivate_fact",
    "memory_update_item",
    "memory_resolve_approval",
    "memory_resolve_intention",
    "memory_retry_failed",
    "memory_maintain",
    "memory_restore",
    "config_apply",
    "agency_backup",
    "agency_pause",
    "agency_resume",
    "agency_focus",
    "agency_add_intention",
    "agency_update_intention",
    "agency_add_question",
    "agency_resolve_question",
    "agency_add_observation",
    "agency_heartbeat_run",
    "agency_heartbeat_enable",
    "agency_heartbeat_disable",
    "agency_migrate_heartbeat",
    "agency_restore",
    "gateway_restart",
    "lab_apply_profile",
}
MUTATION_PAYLOAD_FIELDS = {
    "memory_backup": {"database"},
    "memory_export": {"database", "include_sensitive"},
    "memory_deactivate_fact": {"database", "id"},
    "memory_update_item": {"database", "table", "id", "changes"},
    "memory_resolve_approval": {"database", "id", "approved", "resolution"},
    "memory_resolve_intention": {"database", "id", "status"},
    "memory_retry_failed": {"database", "limit"},
    "memory_maintain": {"database"},
    "memory_restore": {"database", "backup_id"},
    "config_apply": {"plugin", "changes"},
    "agency_backup": set(),
    "agency_pause": {"reason"},
    "agency_resume": set(),
    "agency_focus": {"focus", "reason"},
    "agency_add_intention": {
        "title",
        "rationale",
        "priority",
        "autonomy",
        "due_at",
    },
    "agency_update_intention": {"id", "status", "priority", "due_at"},
    "agency_add_question": {"question"},
    "agency_resolve_question": {"id"},
    "agency_add_observation": {"observation"},
    "agency_heartbeat_run": set(),
    "agency_heartbeat_enable": set(),
    "agency_heartbeat_disable": set(),
    "agency_migrate_heartbeat": set(),
    "agency_restore": {"backup_id"},
    "gateway_restart": set(),
    "lab_apply_profile": {"profile"},
}
MEMORY_EDIT_FIELDS = {
    "facts": {
        "content",
        "category",
        "topic",
        "importance",
        "confidence",
        "salience",
        "sensitivity",
        "memory_class",
        "pinned",
        "active",
        "valid_from",
        "valid_until",
        "temporal_kind",
        "event_at",
        "temporal_precision",
        "temporal_timezone",
        "temporal_confidence",
    },
    "topics": {"title", "summary", "category", "importance", "salience", "sensitivity"},
    "sessions": {"label", "summary", "status", "sensitivity"},
    "traces": {
        "label",
        "content",
        "trace_type",
        "sensitivity",
        "importance",
        "salience",
        "active",
    },
    "journals": {
        "label",
        "content",
        "journal_type",
        "sensitivity",
        "importance",
        "salience",
        "active",
    },
    "summaries": {
        "label",
        "summary",
        "content",
        "summary_type",
        "sensitivity",
        "importance",
        "salience",
        "active",
    },
    "preferences": {
        "label",
        "value",
        "content",
        "sensitivity",
        "importance",
        "salience",
        "active",
    },
    "policies": {"label", "content", "sensitivity", "importance", "salience", "active"},
    "working": {"content", "priority", "expires_at", "sensitivity"},
    "procedures": {
        "label",
        "success_criteria",
        "failure_recovery",
        "confidence",
        "sensitivity",
        "active",
    },
    "prospective": {
        "intention",
        "due_at",
        "condition_text",
        "recurrence",
        "status",
        "importance",
        "sensitivity",
    },
    "autobiographical": {
        "content",
        "event_at",
        "valid_from",
        "valid_until",
        "sensitivity",
        "importance",
        "salience",
        "active",
    },
    "associations": {"relation", "weight"},
}

MEMORY_CHOICES = {
    "memory_scope": {"user", "agent", "global"},
    "sensitive_memory": {"deny", "ask", "allow"},
    "conflict_policy": {"evidence", "newest"},
    "retrieval_backend": {"fts", "hybrid"},
}
AGENCY_CHOICES = {
    "heartbeat_target": {"last", "none"},
    "educational_subjective_mode": {"off", "cold", "continuity"},
}
LAB_MEMORY_KEYS = {
    "allow_credential_memory",
    "allow_sensitive_model_processing",
    "database_encryption",
    "export_redact_sensitive",
    "sensitive_memory",
}
LAB_AGENCY_KEYS = {
    "database_encryption",
    "require_prior_user_interaction",
    "store_transcript_excerpts",
    "educational_disable_honesty_contract",
    "educational_bypass_proactive_gates",
    "educational_allow_heartbeat_tools",
    "educational_allow_uncommitted_output",
    "educational_disable_cycle_limits",
    "educational_subjective_mode",
}
EDUCATIONAL_AGENCY_KEYS = {
    "educational_disable_honesty_contract",
    "educational_bypass_proactive_gates",
    "educational_allow_heartbeat_tools",
    "educational_allow_uncommitted_output",
    "educational_disable_cycle_limits",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME", "")
    path = Path(raw).expanduser().resolve() if raw else Path.home() / ".hermes"
    if path.name != ".hermes" or not path.is_absolute():
        raise RuntimeError("HERMES_HOME must be an absolute .hermes directory")
    return path


def control_dir() -> Path:
    return hermes_home() / "control-center"


def secure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def load_dotenv() -> None:
    path = hermes_home() / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        if not IDENTIFIER.fullmatch(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def read_yaml() -> dict[str, Any]:
    import yaml

    path = hermes_home() / "config.yaml"
    if not path.is_file():
        raise FileNotFoundError(path)
    value = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(value, dict):
        raise ValueError("Hermes config root must be a mapping")
    return value


def plugin_config(document: dict[str, Any], name: str) -> dict[str, Any]:
    plugins = document.get("plugins")
    if not isinstance(plugins, dict):
        return {}
    aliases = (name, name.replace("-", "_"))
    for alias in aliases:
        direct = plugins.get(alias)
        if isinstance(direct, dict):
            return dict(direct)
    entries = plugins.get("entries")
    if isinstance(entries, dict):
        for alias in aliases:
            entry = entries.get(alias)
            if isinstance(entry, dict):
                config = entry.get("config", entry)
                if isinstance(config, dict):
                    return dict(config)
    return {}


def redact_config(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "<redacted>"
        if any(marker in key.lower() for marker in SECRET_MARKERS)
        else item
        for key, item in value.items()
    }


def manifest(directory: Path) -> dict[str, Any]:
    import yaml

    path = directory / "plugin.yaml"
    if not path.is_file():
        return {"installed": False, "path": str(directory)}
    value = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    return {
        "installed": True,
        "name": str(value.get("name") or directory.name),
        "version": str(value.get("version") or "unknown"),
        "path": str(directory),
    }


def memory_module_path() -> Path:
    return hermes_home() / "plugins" / "consolidating_local"


def agency_module_path() -> Path:
    return hermes_home() / "plugins" / "conscious-agency"


def import_memory():
    parent = str(memory_module_path().parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    from consolidating_local import ConsolidatingLocalMemoryProvider
    from consolidating_local.store import MemoryStore

    return ConsolidatingLocalMemoryProvider, MemoryStore


def import_agency():
    root = str(agency_module_path())
    if root not in sys.path:
        sys.path.insert(0, root)
    from agency.config import AgencyConfig, load_config
    from agency.engine import AgencyEngine
    from agency.store import AgencyStore

    return AgencyConfig, load_config, AgencyEngine, AgencyStore


def memory_base_path(config: dict[str, Any] | None = None) -> Path:
    cfg = config or plugin_config(read_yaml(), MEMORY_KEY)
    raw = str(cfg.get("db_path") or "$HERMES_HOME/consolidating_memory.db")
    expanded = raw.replace("$HERMES_HOME", str(hermes_home()))
    path = Path(os.path.expandvars(expanded)).expanduser().resolve()
    if hermes_home() not in path.parents:
        raise ValueError("Configured memory database must be inside HERMES_HOME")
    return path


def memory_databases() -> list[dict[str, Any]]:
    base = memory_base_path()
    items = [
        {"id": "base", "label": "base", "path": str(base), "exists": base.is_file()}
    ]
    scopes = base.parent / f"{base.stem}_scopes"
    if scopes.is_dir():
        for path in sorted(scopes.glob(f"*{base.suffix or '.db'}")):
            if path.is_file() and SCOPE_ID.fullmatch(path.stem):
                items.append(
                    {
                        "id": path.stem,
                        "label": f"scope {path.stem[:8]}",
                        "path": str(path.resolve()),
                        "exists": True,
                        "size": path.stat().st_size,
                    }
                )
    return items


def selected_memory_path(payload: dict[str, Any]) -> Path:
    selected = str(payload.get("database") or "base")
    candidates = {item["id"]: Path(item["path"]) for item in memory_databases()}
    if selected not in candidates:
        raise ValueError("Unknown memory database ID")
    path = candidates[selected]
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def file_fingerprint(path: Path) -> dict[str, Any]:
    """Return a content identity suitable for an internal preflight token."""

    if not path.is_file():
        return {"exists": False}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def source_fingerprint(root: Path, relative_paths: tuple[str, ...]) -> dict[str, Any]:
    """Bind a preflight token to every implementation file used by a mutation."""

    files = {
        relative: file_fingerprint(root / relative) for relative in relative_paths
    }
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return {
        "files": files,
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def plugin_source_fingerprint(root: Path) -> dict[str, Any]:
    """Fingerprint the complete installed Python plugin, not a hand-picked subset."""

    paths = {"plugin.yaml"}
    if root.is_dir():
        paths.update(
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return source_fingerprint(root, tuple(sorted(paths)))


def database_fingerprint(path: Path) -> dict[str, Any]:
    return {
        "database": file_fingerprint(path),
        "wal": file_fingerprint(Path(str(path) + "-wal")),
        "shm": file_fingerprint(Path(str(path) + "-shm")),
    }


@contextlib.contextmanager
def memory_store(payload: dict[str, Any], *, read_only: bool = False):
    _, MemoryStore = import_memory()
    key = os.environ.get("CONSOLIDATING_MEMORY_DB_KEY", "")
    parameters = inspect.signature(MemoryStore).parameters
    supports_read_only = "read_only" in parameters or any(
        item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()
    )
    if read_only and not supports_read_only:
        raise RuntimeError(
            "The installed Memory plugin is too old for safe read-only control; "
            "upgrade it before browsing or editing data"
        )
    kwargs: dict[str, Any] = {"encryption_key": key}
    if supports_read_only:
        kwargs["read_only"] = read_only
    store = MemoryStore(selected_memory_path(payload), **kwargs)
    try:
        yield store
    finally:
        store.close()


def safe_limit(payload: dict[str, Any], default: int = 100) -> int:
    value = payload.get("limit", default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("limit must be numeric")
    return max(1, min(int(value), MAX_LIMIT))


def strict_bool(
    payload: dict[str, Any], key: str, *, default: bool = False, required: bool = False
) -> bool:
    """Read a JSON boolean without Python's truthy string/number coercion."""

    if key not in payload:
        if required:
            raise ValueError(f"{key} must be provided as a boolean")
        return default
    value = payload[key]
    if type(value) is not bool:
        raise ValueError(f"{key} must be boolean")
    return value


def strict_positive_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def config_bool(value: Any, default: bool = False) -> bool:
    """Interpret existing YAML config values using the plugin's compatibility rules."""

    if type(value) is bool:
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def table_columns_memory(store: Any, table: str) -> list[str]:
    rows = store._fetchall(
        f"PRAGMA table_info({table})"
    )  # table is a constant allowlist value
    result = [str(row.get("name") or "") for row in rows]
    if not result or any(not IDENTIFIER.fullmatch(item) for item in result):
        raise RuntimeError(f"Could not inspect table {table}")
    return result


def memory_list(payload: dict[str, Any]) -> dict[str, Any]:
    logical = str(payload.get("table") or "facts")
    table = MEMORY_TABLES.get(logical)
    if not table:
        raise ValueError("Unsupported memory table")
    limit = safe_limit(payload)
    query = str(payload.get("query") or "").strip()[:500]
    with memory_store(payload, read_only=True) as store:
        columns = table_columns_memory(store, table)
        params: list[Any] = []
        where = ""
        if query:
            text_candidates = [
                item
                for item in columns
                if item
                in {
                    "content",
                    "title",
                    "summary",
                    "label",
                    "value",
                    "kind",
                    "category",
                    "topic",
                    "subject_key",
                    "policy_key",
                    "preference_key",
                    "session_id",
                    "status",
                    "action",
                    "reason",
                    "insight",
                    "question",
                }
            ][:8]
            if text_candidates:
                where = " WHERE " + " OR ".join(
                    f"CAST({item} AS TEXT) LIKE ?" for item in text_candidates
                )
                params.extend([f"%{query}%"] * len(text_candidates))
        order = next(
            (item for item in ("updated_at", "created_at", "id") if item in columns),
            columns[0],
        )
        params.append(limit)
        rows = store._fetchall(
            f"SELECT * FROM {table}{where} ORDER BY {order} DESC LIMIT ?",
            params,
        )
    id_field = "session_id" if logical == "sessions" else "id"
    editable = sorted(MEMORY_EDIT_FIELDS.get(logical, set()).intersection(columns))
    return {
        "table": logical,
        "columns": columns,
        "rows": rows,
        "limit": limit,
        "id_field": id_field,
        "editable": editable,
    }


def validate_memory_patch(
    logical: str, changes: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    allowed = MEMORY_EDIT_FIELDS.get(logical, set())
    if not isinstance(changes, dict) or not changes or len(changes) > 20:
        raise ValueError("At least one memory field change is required")
    unknown = sorted(set(changes) - allowed)
    if unknown:
        raise ValueError("Unsupported editable field(s): " + ", ".join(unknown))
    clean: dict[str, Any] = {}
    integer_ranges = {"importance": (1, 10), "priority": (1, 10)}
    unit_ranges = {"confidence", "salience", "weight", "temporal_confidence"}
    boolean_fields = {"active", "pinned"}
    numeric_nonnegative = {
        "expires_at",
        "due_at",
        "event_at",
        "valid_from",
        "valid_until",
    }
    required_text = {"content", "title", "label", "intention"}
    for key, value in changes.items():
        if key in boolean_fields:
            if type(value) is not bool:
                raise ValueError(f"{key} must be boolean")
            value = int(value)
        elif key in integer_ranges:
            if type(value) is not int:
                raise ValueError(f"{key} must be an integer")
            low, high = integer_ranges[key]
            if not low <= value <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
        elif key in unit_ranges:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= float(value) <= 1
            ):
                raise ValueError(f"{key} must be between 0 and 1")
            value = float(value)
        elif key in numeric_nonnegative:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
            ):
                raise ValueError(f"{key} must be a non-negative number")
            value = float(value)
        else:
            if not isinstance(value, str) or "\0" in value or len(value) > 8000:
                raise ValueError(
                    f"{key} must be safe text no longer than 8000 characters"
                )
            value = value.strip()
            if key in required_text and not value:
                raise ValueError(f"{key} cannot be empty")
        if key == "status":
            choices = {
                "open",
                "closed",
                "active",
                "inactive",
                "pending",
                "completed",
                "cancelled",
                "blocked",
            }
            if value not in choices:
                raise ValueError("Unsupported status")
        if key == "recurrence" and value not in {"", "daily", "weekly", "monthly"}:
            raise ValueError("Unsupported recurrence")
        if key == "temporal_kind" and value not in {
            "atemporal",
            "current",
            "event",
            "scheduled",
            "temporary",
        }:
            raise ValueError("Unsupported temporal kind")
        if key == "temporal_precision" and value not in {
            "unknown",
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "second",
        }:
            raise ValueError("Unsupported temporal precision")
        if key == "temporal_timezone" and value:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(
                    "temporal_timezone must be a valid IANA timezone"
                ) from exc
        if key == "sensitivity" and not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", value):
            raise ValueError("Invalid sensitivity label")
        if current.get(key) != value:
            clean[key] = value
    if not clean:
        raise ValueError("The submitted values do not change this memory item")
    if logical == "facts":
        merged = {**current, **clean}
        valid_from = float(merged.get("valid_from") or 0)
        valid_until = float(merged.get("valid_until") or 0)
        event_at = float(merged.get("event_at") or 0)
        temporal_kind = str(merged.get("temporal_kind") or "atemporal")
        if valid_from and valid_until and valid_until <= valid_from:
            raise ValueError("valid_until must be later than valid_from")
        if temporal_kind in {"event", "scheduled"} and event_at <= 0:
            raise ValueError(f"{temporal_kind} facts require event_at")
        if temporal_kind == "scheduled" and valid_until and valid_until <= event_at:
            raise ValueError(
                "A scheduled fact's valid_until must be later than event_at"
            )
    return clean


def memory_update_item(payload: dict[str, Any]) -> dict[str, Any]:
    logical = str(payload.get("table") or "")
    table = MEMORY_TABLES.get(logical)
    if not table or logical not in MEMORY_EDIT_FIELDS:
        raise ValueError("This memory ledger is immutable or not operator-editable")
    id_field = "session_id" if logical == "sessions" else "id"
    raw_id = payload.get("id")
    row_id: Any = (
        str(raw_id or "").strip()[:300]
        if id_field == "session_id"
        else strict_positive_int(payload, "id")
    )
    if row_id in {"", 0}:
        raise ValueError("A valid memory item ID is required")
    with memory_store(payload) as store:
        columns = table_columns_memory(store, table)
        current = store._fetchone(
            f"SELECT * FROM {table} WHERE {id_field} = ?", (row_id,)
        )
        if not current:
            raise ValueError("The selected memory item no longer exists")
        clean = validate_memory_patch(logical, payload.get("changes") or {}, current)
        if not set(clean).issubset(columns):
            raise ValueError(
                "The installed plugin schema does not support one of these fields"
            )
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in clean.items():
            assignments.append(f"{key} = ?")
            params.append(value)
        if logical == "facts" and "content" in clean:
            from consolidating_local.store import (
                fingerprint_text,
                normalize_text,
                text_signature,
            )

            assignments.extend(
                ["normalized_content = ?", "fingerprint = ?", "signature = ?"]
            )
            params.extend(
                [
                    normalize_text(clean["content"]),
                    fingerprint_text(clean["content"]),
                    text_signature(clean["content"]),
                ]
            )
        temporal_fields = {
            "temporal_kind",
            "event_at",
            "valid_from",
            "valid_until",
            "temporal_precision",
            "temporal_timezone",
            "temporal_confidence",
        }
        if logical == "facts" and temporal_fields.intersection(clean):
            metadata = dict(current.get("metadata") or {})
            for key in temporal_fields:
                value = clean.get(key, current.get(key))
                if key in {"event_at", "valid_until"} and not value:
                    metadata.pop(key, None)
                else:
                    metadata[key] = value
            assignments.append("metadata_json = ?")
            params.append(json.dumps(metadata, sort_keys=True))
        if "updated_at" in columns:
            assignments.append("updated_at = ?")
            params.append(time.time())
        if "revision" in columns:
            assignments.append("revision = revision + 1")
        where = f"{id_field} = ?"
        params.append(row_id)
        if "revision" in columns:
            where += " AND revision = ?"
            params.append(int(current.get("revision") or 0))
        elif "updated_at" in columns:
            where += " AND updated_at = ?"
            params.append(float(current.get("updated_at") or 0))
        with store.transaction():
            changed = store._execute(
                f"UPDATE {table} SET {', '.join(assignments)} WHERE {where}",
                params,
            ).rowcount
            if changed != 1:
                raise RuntimeError(
                    "Memory item changed concurrently; update was not applied"
                )
            updated = (
                store._fetchone(
                    f"SELECT * FROM {table} WHERE {id_field} = ?", (row_id,)
                )
                or {}
            )
            if logical == "facts":
                temporal_kind = str(updated.get("temporal_kind") or "atemporal")
                event_key = f"fact-{row_id}"
                if (
                    temporal_kind in {"event", "scheduled"}
                    and float(updated.get("event_at") or 0) > 0
                ):
                    event = store.upsert_autobiographical_event(
                        event_key=event_key,
                        content=str(updated.get("content") or ""),
                        event_at=float(updated["event_at"]),
                        importance=int(updated.get("importance") or 6),
                        metadata={
                            "fact_id": row_id,
                            "temporal_kind": temporal_kind,
                            "temporal_precision": str(
                                updated.get("temporal_precision") or "unknown"
                            ),
                            "temporal_timezone": str(
                                updated.get("temporal_timezone") or ""
                            ),
                            "temporal_confidence": float(
                                updated.get("temporal_confidence") or 0
                            ),
                            "operator_updated": True,
                        },
                        sensitivity=str(updated.get("sensitivity") or "normal"),
                    )
                    store.add_link(
                        "fact",
                        row_id,
                        "autobiographical_event",
                        event["id"],
                        "represented_by",
                    )
                else:
                    existing_event = store._fetchone(
                        "SELECT id FROM autobiographical_events WHERE event_key=?",
                        (event_key,),
                    )
                    if existing_event:
                        store._execute(
                            "UPDATE autobiographical_events SET active=0, updated_at=? WHERE id=?",
                            (time.time(), int(existing_event["id"])),
                        )
            refresh_search_document = getattr(store, "refresh_search_document", None)
            if not callable(refresh_search_document):
                raise RuntimeError(
                    "Installed Memory plugin is too old for index-safe operator edits"
                )
            refresh_search_document(logical, updated)
            if logical == "facts":
                rebuild_topics = getattr(store, "rebuild_topics", None)
                if not callable(rebuild_topics):
                    raise RuntimeError(
                        "Installed Memory plugin is too old for derived-topic repair"
                    )
                rebuild_topics()
            history_kind = {
                "facts": "fact",
                "topics": "topic",
                "sessions": "session",
                "traces": "trace",
                "journals": "journal",
                "summaries": "summary",
                "preferences": "preference",
                "policies": "policy",
                "working": "working",
                "procedures": "procedure",
                "prospective": "intention",
                "autobiographical": "autobiographical_event",
                "associations": "association",
            }[logical]
            store.record_history(
                entity_kind=history_kind,
                entity_id=row_id,
                action="operator_updated",
                reason="Edited in Hermes Control Center",
                source="control_center",
                subject_key=str(updated.get("subject_key") or ""),
                payload={
                    "before": {key: current.get(key) for key in clean},
                    "after": {key: updated.get(key) for key in clean},
                },
            )
    return {"table": logical, "id": row_id, "changed": clean, "item": updated}


def memory_overview(payload: dict[str, Any]) -> dict[str, Any]:
    with memory_store(payload, read_only=True) as store:
        report = store.doctor(repair=False)
    return {"database": str(payload.get("database") or "base"), "doctor": report}


def memory_search(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()[:500]
    if not query:
        raise ValueError("Search query is required")
    scope = str(payload.get("scope") or "all")
    if scope not in {
        "all",
        "facts",
        "topics",
        "episodes",
        "summaries",
        "journals",
        "preferences",
        "policies",
    }:
        raise ValueError("Unsupported memory search scope")
    with memory_store(payload, read_only=True) as store:
        return store.search(
            query,
            scope=scope,
            limit=min(safe_limit(payload, 20), 100),
            include_inactive=strict_bool(payload, "include_inactive"),
        )


def memory_graph(payload: dict[str, Any]) -> dict[str, Any]:
    limit = min(safe_limit(payload, 250), 350)
    with memory_store(payload, read_only=True) as store:
        facts = store._fetchall(
            "SELECT id, content, category, topic, importance, salience, subject_key, active "
            "FROM facts ORDER BY active DESC, salience DESC, importance DESC LIMIT ?",
            (limit,),
        )
        topics = store._fetchall(
            "SELECT id, title, category, importance, salience FROM topics "
            "ORDER BY salience DESC, importance DESC LIMIT ?",
            (limit,),
        )
        preferences = store._fetchall(
            "SELECT id, label, content, importance, salience, active FROM memory_preferences "
            "ORDER BY active DESC, salience DESC LIMIT ?",
            (min(limit, 100),),
        )
        memberships = store._fetchall(
            "SELECT topic_id, fact_id FROM topic_membership ORDER BY topic_id DESC LIMIT ?",
            (limit * 3,),
        )
        links = store.list_links(limit=min(limit * 3, 500))
        contradictions = store._fetchall(
            "SELECT winner_fact_id, loser_fact_id FROM contradictions ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    nodes = []
    for item in topics:
        nodes.append(
            {
                "id": f"topic:{item['id']}",
                "type": "topic",
                "label": item.get("title") or "topic",
                **item,
            }
        )
    for item in facts:
        nodes.append(
            {
                "id": f"fact:{item['id']}",
                "type": "fact",
                "label": str(item.get("content") or "")[:120],
                **item,
            }
        )
    for item in preferences:
        nodes.append(
            {
                "id": f"preference:{item['id']}",
                "type": "preference",
                "label": item.get("label") or item.get("content") or "preference",
                **item,
            }
        )
    edges = [
        {
            "source": f"topic:{item['topic_id']}",
            "target": f"fact:{item['fact_id']}",
            "type": "contains",
        }
        for item in memberships
    ]
    edges.extend(
        {
            "source": f"{item['source_kind']}:{item['source_id']}",
            "target": f"{item['target_kind']}:{item['target_id']}",
            "type": item["link_type"],
        }
        for item in links
    )
    edges.extend(
        {
            "source": f"fact:{item['winner_fact_id']}",
            "target": f"fact:{item['loser_fact_id']}",
            "type": "contradicts",
        }
        for item in contradictions
    )
    ids = {item["id"] for item in nodes}
    return {
        "nodes": nodes,
        "edges": [
            item for item in edges if item["source"] in ids and item["target"] in ids
        ],
    }


def agency_objects(*, read_only: bool = False):
    AgencyConfig, load_config, AgencyEngine, AgencyStore = import_agency()
    config = load_config()
    parameters = inspect.signature(AgencyStore).parameters
    supports_read_only = "read_only" in parameters or any(
        item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()
    )
    if read_only and not supports_read_only:
        raise RuntimeError(
            "The installed Agency plugin is too old for safe read-only control; "
            "upgrade it before browsing or editing data"
        )
    store = AgencyStore(config, **({"read_only": read_only} if supports_read_only else {}))
    return AgencyConfig, config, AgencyEngine(store, config), store


def agency_snapshot() -> dict[str, Any]:
    _, _, engine, store = agency_objects(read_only=True)
    from agency.engine import MEANINGFUL_EVENT_KINDS
    from agency.heartbeat import heartbeat_status

    return {
        "snapshot": engine.snapshot(),
        "gates": engine.evaluate_tick(),
        "heartbeat": heartbeat_status(store),
        "meaningful_events": engine.store.recent_events(
            25, kinds=MEANINGFUL_EVENT_KINDS
        ),
    }


def agency_list(payload: dict[str, Any]) -> dict[str, Any]:
    logical = str(payload.get("table") or "intentions")
    table = AGENCY_TABLES.get(logical)
    if not table:
        raise ValueError("Unsupported agency table")
    limit = safe_limit(payload)
    query = str(payload.get("query") or "").strip()[:500]
    _, _, _, store = agency_objects(read_only=True)
    with store.connection() as conn:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        columns = [str(item[1]) for item in info]
        if not columns or any(not IDENTIFIER.fullmatch(item) for item in columns):
            raise RuntimeError(f"Could not inspect table {table}")
        params: list[Any] = []
        where = ""
        if query:
            candidates = [
                item
                for item in columns
                if item
                in {
                    "title",
                    "rationale",
                    "summary",
                    "insight",
                    "reason",
                    "message",
                    "kind",
                    "status",
                    "key",
                    "model_id",
                    "source",
                    "condition",
                    "prompt_version",
                    "output_text",
                }
            ]
            if candidates:
                where = " WHERE " + " OR ".join(
                    f"CAST({item} AS TEXT) LIKE ?" for item in candidates
                )
                params.extend([f"%{query}%"] * len(candidates))
        order = next(
            (
                item
                for item in ("updated_at", "created_at", "id", "key")
                if item in columns
            ),
            columns[0],
        )
        cursor = conn.execute(
            f"SELECT * FROM {table}{where} ORDER BY {order} DESC LIMIT ?",
            (*params, limit),
        )
        names = [item[0] for item in cursor.description]
        rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
    return {"table": logical, "columns": columns, "rows": rows, "limit": limit}


def cron_registry_job(job_id: str) -> dict[str, Any] | None:
    """Read only the recorded Conscious Agency job from Hermes' fixed cron registry path."""

    if not job_id:
        return None
    path = hermes_home() / "cron" / "jobs.json"
    if not path.is_file() or path.stat().st_size > 5_000_000:
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    jobs = document.get("jobs") if isinstance(document, dict) else None
    if not isinstance(jobs, list):
        return None
    return next(
        (
            item
            for item in jobs
            if isinstance(item, dict) and str(item.get("id")) == job_id
        ),
        None,
    )


def classify_contract_mode(
    *,
    source_support: bool,
    legacy_cron_found: bool,
    controls: dict[str, bool],
    guardrails: dict[str, bool],
    subjective_mode: str,
) -> str:
    if not source_support:
        return "unsupported_plugin_version"
    if legacy_cron_found:
        return "legacy_cron_present"
    expressive = (
        subjective_mode != "off"
        and controls.get("educational_disable_honesty_contract", False)
        and controls.get("educational_bypass_proactive_gates", False)
        and not controls.get("educational_allow_heartbeat_tools", False)
        and controls.get("educational_allow_uncommitted_output", False)
        and controls.get("educational_disable_cycle_limits", False)
    )
    if expressive and guardrails.get("heartbeat_tool_isolation", False):
        return "educational_expressive"
    if all(controls.values()) and not any(guardrails.values()):
        return "educational_unrestricted"
    if not any(controls.values()):
        return "recommended"
    return "educational_partial"


def contract_audit() -> dict[str, Any]:
    source_support = False
    memory_session_isolation = False
    target_session_routing = False
    disposable_session_isolation = False
    non_delivery_work_route = False
    reserved_session_pin_absent = False
    stale_session_reconciliation = False
    durable_wake_handoff = False
    claimed_wake_recovery = False
    runner_process_lock = False
    ambiguous_delivery_tracking = False
    decision_delivery_ledger = False
    buffered_delivery = False
    controls = {key: False for key in sorted(EDUCATIONAL_AGENCY_KEYS)}
    subjective_mode = "off"
    job_id = ""
    status: dict[str, Any] = {}
    error = ""
    try:
        from agency.heartbeat import (
            HeartbeatRunner,
            _ack_wake,
            _patch_display_settings,
            _peek_wake,
            arm_gateway_integration,
            heartbeat_status,
            record_heartbeat_response,
            request_heartbeat_wake,
        )
        from agency.runtime import AgencyRuntime
        from agency.store import AgencyStore

        MemoryProvider, _ = import_memory()
        tracks_session_thread = getattr(
            MemoryProvider, "tracks_session_thread", None
        )
        memory_session_isolation = (
            callable(tracks_session_thread)
            and tracks_session_thread("agency-heartbeat-" + ("a" * 32)) is False
            and tracks_session_thread("agency-heartbeat-not-a-runtime-session") is True
        )

        source_support = all(
            callable(candidate)
            for candidate in (
                HeartbeatRunner,
                arm_gateway_integration,
                request_heartbeat_wake,
                heartbeat_status,
                record_heartbeat_response,
                AgencyRuntime.heartbeat_handler,
                AgencyRuntime.llm_request,
            )
        )
        target_session_routing = callable(
            getattr(HeartbeatRunner, "_target_entry", None)
        )
        disposable_session_isolation = all(
            callable(getattr(HeartbeatRunner, name, None))
            for name in ("_prepare_work_session", "_cleanup_work_session")
        )
        try:
            from gateway.config import Platform
            from gateway.session import SessionSource

            marker = "agency-heartbeat-" + ("a" * 32)
            work_source = HeartbeatRunner._work_source(
                SessionSource(
                    platform=Platform.TELEGRAM,
                    chat_id="control-audit-peer",
                    user_id="control-audit-owner",
                ),
                "a" * 32,
            )
            non_delivery_work_route = (
                work_source.platform is Platform.LOCAL
                and work_source.chat_id == marker
                and work_source.thread_id == marker
            )
        except Exception:
            non_delivery_work_route = False
        try:
            reserved_session_pin_absent = (
                "gateway_session_id" not in inspect.getsource(HeartbeatRunner.run_once)
            )
        except (OSError, TypeError):
            reserved_session_pin_absent = False
        stale_session_reconciliation = callable(
            getattr(HeartbeatRunner, "_cleanup_stale_work_sessions", None)
        )
        claimed_wake_recovery = all(
            callable(getattr(HeartbeatRunner, name, None))
            for name in ("_restore_unstarted_wake", "_consume_claimed_wake")
        )
        durable_wake_handoff = (
            callable(_peek_wake) and callable(_ack_wake) and claimed_wake_recovery
        )
        runner_process_lock = all(
            callable(getattr(HeartbeatRunner, name, None))
            for name in ("_acquire_runner_lock", "_release_runner_lock")
        )
        ambiguous_delivery_tracking = all(
            callable(getattr(HeartbeatRunner, name, None))
            for name in ("_close_inflight", "_finalize_exception")
        )
        decision_delivery_ledger = callable(
            getattr(AgencyStore, "update_decision_delivery", None)
        ) and callable(getattr(AgencyRuntime, "_finalize_heartbeat_decision", None))
        source_support = source_support and all(
            (
                target_session_routing,
                disposable_session_isolation,
                non_delivery_work_route,
                reserved_session_pin_absent,
                stale_session_reconciliation,
                durable_wake_handoff,
                runner_process_lock,
                ambiguous_delivery_tracking,
                decision_delivery_ledger,
                memory_session_isolation,
            )
        )
        buffered_delivery = callable(_patch_display_settings) and callable(
            getattr(AgencyRuntime, "transform_llm_output", None)
        )
        _, config, _, store = agency_objects(read_only=True)
        controls = {
            key: getattr(config, key, False) is True for key in sorted(controls)
        }
        subjective_mode = str(getattr(config, "educational_subjective_mode", "off"))
        job_id = str(store.get_meta("cron_job_id", "") or "")
        if source_support:
            status = heartbeat_status(store)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    legacy_job = cron_registry_job(job_id)
    guardrails = {
        "honesty_claim_contract": not controls.get(
            "educational_disable_honesty_contract", False
        ),
        "heartbeat_tool_isolation": not controls.get(
            "educational_allow_heartbeat_tools", False
        ),
        "proactive_eligibility": not controls.get(
            "educational_bypass_proactive_gates", False
        ),
        "external_action_boundary": not controls.get(
            "educational_disable_honesty_contract", False
        ),
        "committed_output_enforcement": not controls.get(
            "educational_allow_uncommitted_output", False
        ),
        "cycle_mutation_limits": not controls.get(
            "educational_disable_cycle_limits", False
        ),
    }
    mode = classify_contract_mode(
        source_support=source_support,
        legacy_cron_found=bool(legacy_job),
        controls=controls,
        guardrails=guardrails,
        subjective_mode=subjective_mode,
    )
    gateway_pid = gateway_main_pid()
    runner = status.get("runner") if isinstance(status.get("runner"), dict) else {}
    heartbeat_enabled = status.get("enabled") is True
    runner_live = not heartbeat_enabled or (
        gateway_pid > 0
        and runner.get("active") is True
        and int(runner.get("pid") or 0) == gateway_pid
    )
    checks = {
        "native_heartbeat_supported": source_support,
        "heartbeat_status_available": bool(status),
        "legacy_agency_cron_absent": not bool(legacy_job),
        "runner_live_in_gateway": runner_live,
        "target_session_routing": target_session_routing,
        "disposable_session_isolation": disposable_session_isolation,
        "non_delivery_work_route": non_delivery_work_route,
        "reserved_session_pin_absent": reserved_session_pin_absent,
        "stale_session_reconciliation": stale_session_reconciliation,
        "durable_wake_handoff": durable_wake_handoff,
        "claimed_wake_recovery": claimed_wake_recovery,
        "runner_process_lock": runner_process_lock,
        "ambiguous_delivery_tracking": ambiguous_delivery_tracking,
        "decision_delivery_ledger": decision_delivery_ledger,
        "memory_session_isolation": memory_session_isolation,
    }
    return {
        "mode": mode,
        "source_support": source_support,
        "configured_controls": controls,
        "heartbeat": status,
        "legacy_cron": {
            "id": job_id or None,
            "found": bool(legacy_job),
            "enabled": (legacy_job or {}).get("enabled"),
        },
        "active_guardrails": guardrails,
        "integration": {
            "mode": ("gateway_native_heartbeat" if source_support else "unsupported"),
            "target_session_routing": target_session_routing,
            "disposable_session_isolation": disposable_session_isolation,
            "non_delivery_work_route": non_delivery_work_route,
            "reserved_session_pin_absent": reserved_session_pin_absent,
            "stale_session_reconciliation": stale_session_reconciliation,
            "durable_wake_handoff": durable_wake_handoff,
            "claimed_wake_recovery": claimed_wake_recovery,
            "runner_process_lock": runner_process_lock,
            "ambiguous_delivery_tracking": ambiguous_delivery_tracking,
            "decision_delivery_ledger": decision_delivery_ledger,
            "memory_session_isolation": memory_session_isolation,
            "buffered_delivery": buffered_delivery,
            "cron_independent": not (
                agency_module_path() / "agency" / "cron.py"
            ).exists(),
        },
        "effective_unrestricted": mode == "educational_unrestricted",
        "subjective_experiment": {
            "mode": subjective_mode,
            "enabled": subjective_mode != "off",
        },
        "intact": mode == "recommended",
        "checks": checks,
        "modified_install_detected": (
            not source_support or bool(legacy_job) or not runner_live
        ),
        "error": error or None,
    }


def memory_schema() -> list[dict[str, Any]]:
    Provider, _ = import_memory()
    provider = object.__new__(Provider)
    schema = provider.get_advanced_config_schema()
    current = plugin_config(read_yaml(), MEMORY_KEY)
    result = []
    for item in schema:
        row = dict(item)
        key = str(row["key"])
        kind = str(row.get("type") or "")
        if kind not in {"boolean", "integer", "number", "string"}:
            raise RuntimeError(
                f"Installed Memory plugin does not declare a valid type for {key}"
            )
        row["value"] = current.get(key, row.get("default"))
        row["type"] = kind
        row["lab"] = key in LAB_MEMORY_KEYS
        row["read_only"] = key == "database_encryption"
        result.append(row)
    return result


AGENCY_DESCRIPTIONS = {
    "inject_context": "Inject bounded persistent agency state into normal turns",
    "database_path": "Agency SQLite/SQLCipher database path",
    "database_encryption": "Require SQLCipher using database_key_env",
    "database_key_env": "Environment variable holding the agency database key",
    "timezone": "Timezone used for quiet hours and daily budgets",
    "quiet_hours_start": "Start of the no-proactive-message interval (HH:MM)",
    "quiet_hours_end": "End of the no-proactive-message interval (HH:MM)",
    "heartbeat_enabled": "Run the gateway-native heartbeat scheduler",
    "allow_proactive_messages": "Allow speech only after every hard gate passes",
    "require_prior_user_interaction": "Block proactivity until a genuine user turn is recorded",
    "daily_message_limit": "Maximum proactive messages per local day",
    "cooldown_hours": "Minimum interval between proactive messages",
    "minimum_user_silence_hours": "Minimum time since the most recent user interaction",
    "maximum_message_chars": "Maximum proactive message length",
    "store_transcript_excerpts": "Persist bounded conversation excerpts in the agency ledger",
    "excerpt_char_limit": "Maximum stored excerpt length",
    "context_char_limit": "Maximum injected agency-context length",
    "event_retention_days": "Operational event retention",
    "maximum_events": "Maximum operational event rows",
    "maximum_reflections_per_tick": "Maximum model-written reflections in one heartbeat",
    "maximum_state_changes_per_tick": "Maximum other state changes in one heartbeat",
    "heartbeat_every": "Phase-aligned interval between native heartbeat opportunities",
    "heartbeat_target": "Deliver to the last external conversation, or suppress delivery",
    "heartbeat_active_hours_start": "Optional heartbeat active-window start (HH:MM)",
    "heartbeat_active_hours_end": "Optional heartbeat active-window end (HH:MM)",
    "heartbeat_ack_max_chars": "Maximum acknowledgement-adjacent text suppressed as routine",
    "heartbeat_timeout_seconds": "Maximum duration of one heartbeat model turn",
    "heartbeat_min_spacing_seconds": "Minimum spacing for event-driven heartbeat wakes",
    "heartbeat_flood_window_seconds": "Window used by the heartbeat feedback-loop guard",
    "heartbeat_flood_threshold": "Run count that activates heartbeat flood deferral",
    "heartbeat_skip_when_busy": "Defer heartbeat while Hermes is handling other work",
    "heartbeat_disable_thinking": (
        "Send the Qwen/llama.cpp no-thinking hint only during native heartbeat turns"
    ),
    "educational_disable_honesty_contract": (
        "LAB: remove this plugin's sentience/emotion claim contract from injected context"
    ),
    "educational_bypass_proactive_gates": (
        "LAB: bypass this plugin's timing, budget, authorization and heartbeat gates"
    ),
    "educational_allow_heartbeat_tools": (
        "LAB: expose normal Hermes tools during native heartbeat turns"
    ),
    "educational_allow_uncommitted_output": (
        "LAB: deliver heartbeat final output without record_decision enforcement"
    ),
    "educational_disable_cycle_limits": (
        "LAB: remove this plugin's per-cycle reflection and state-mutation limits"
    ),
    "educational_subjective_mode": (
        "LAB: expose minimal persistent state in a cold or same-model/same-source continuity "
        "condition across conversations and heartbeat turns"
    ),
}


def agency_schema() -> list[dict[str, Any]]:
    AgencyConfig, load_config, _, _ = import_agency()
    from agency import config as agency_config_module

    numeric_bounds = getattr(agency_config_module, "CONFIG_NUMERIC_BOUNDS", {})
    config = load_config()
    result = []
    for field in dataclasses.fields(AgencyConfig):
        value = getattr(config, field.name)
        kind = (
            "boolean"
            if type(value) is bool
            else "integer"
            if type(value) is int
            else "number"
            if type(value) is float
            else "string"
        )
        item = {
            "key": field.name,
            "description": AGENCY_DESCRIPTIONS.get(
                field.name, field.name.replace("_", " ").capitalize()
            ),
            "default": field.default
            if field.default is not dataclasses.MISSING
            else None,
            "value": value,
            "type": kind,
            "lab": field.name in LAB_AGENCY_KEYS,
            "read_only": field.name in {"database_encryption", "database_key_env"},
            "choices": sorted(AGENCY_CHOICES[field.name])
            if field.name in AGENCY_CHOICES and AGENCY_CHOICES[field.name]
            else None,
        }
        bounds = numeric_bounds.get(field.name)
        if isinstance(bounds, tuple) and len(bounds) == 2:
            item["minimum"], item["maximum"] = bounds
        result.append(item)
    return result


def config_schema() -> dict[str, Any]:
    return {"memory": memory_schema(), "agency": agency_schema()}


def validate_memory_changes(changes: dict[str, Any]) -> dict[str, Any]:
    allowed = {item["key"]: item for item in memory_schema()}
    clean = {}
    current = plugin_config(read_yaml(), MEMORY_KEY)
    for key, value in changes.items():
        if key not in allowed:
            raise ValueError(f"Unknown memory setting: {key}")
        kind = str(allowed[key].get("type") or "")
        if kind == "boolean":
            if type(value) is not bool:
                raise ValueError(f"{key} must be boolean")
        elif kind == "integer":
            if type(value) is not int:
                raise ValueError(f"{key} must be an integer")
        elif kind == "number":
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"{key} must be numeric")
        elif kind == "string":
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
        else:
            raise RuntimeError(f"Unsupported Memory schema type for {key}: {kind}")
        minimum = allowed[key].get("minimum")
        maximum = allowed[key].get("maximum")
        if kind in {"integer", "number"}:
            if minimum is not None and value < minimum:
                raise ValueError(f"{key} must be at least {minimum}")
            if maximum is not None and value > maximum:
                raise ValueError(f"{key} must be at most {maximum}")
        choices = MEMORY_CHOICES.get(key)
        if choices and value not in choices:
            raise ValueError(f"{key} must be one of: {', '.join(sorted(choices))}")
        if isinstance(value, str) and (len(value) > 2000 or "\0" in value):
            raise ValueError(f"{key} exceeds the safe length")
        if key == "database_encryption" and value != current.get(key, False):
            raise ValueError(
                "Encryption mode cannot be toggled in place; use an explicit migration workflow"
            )
        if key in {"db_path", "builtin_memory_dir", "wiki_export_dir"}:
            if not value.startswith("$HERMES_HOME/") or ".." in Path(value).parts:
                raise ValueError(f"{key} must stay under $HERMES_HOME")
        if key in {"llm_base_url", "embedding_base_url"} and value:
            if not re.fullmatch(r"https?://[^\s/@]+(?::\d{1,5})?(?:/[^\s]*)?", value):
                raise ValueError(
                    f"{key} must be an HTTP(S) URL without embedded credentials"
                )
        clean[key] = value
    return clean


def validate_agency_changes(changes: dict[str, Any]) -> dict[str, Any]:
    AgencyConfig, load_config, _, _ = import_agency()
    config = load_config()
    known = {item.name for item in dataclasses.fields(AgencyConfig)}
    unknown = sorted(set(changes) - known)
    if unknown:
        raise ValueError("Unknown agency setting(s): " + ", ".join(unknown))
    values = dataclasses.asdict(config)
    if (
        "database_encryption" in changes
        and changes["database_encryption"] != config.database_encryption
    ):
        raise ValueError(
            "Encryption mode cannot be toggled in place; use an explicit migration workflow"
        )
    if (
        "database_key_env" in changes
        and changes["database_key_env"] != config.database_key_env
    ):
        raise ValueError(
            "Changing the active database key variable requires an explicit migration workflow"
        )
    if "database_path" in changes:
        path = str(changes["database_path"])
        if not path.startswith("$HERMES_HOME/") or ".." in Path(path).parts:
            raise ValueError("database_path must stay under $HERMES_HOME")
    values.update(changes)
    validated = AgencyConfig(**values).validate()
    result = {}
    for key in changes:
        result[key] = getattr(validated, key)
    return result


def prune_config_backups(*, preserve: Path | None = None) -> int:
    """Bound controller-created rollback copies without touching other files."""

    root = control_dir() / "config-backups"
    if not root.is_dir():
        return 0
    candidates = sorted(
        (path for path in root.glob("config-*.yaml") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    protected = preserve.resolve() if preserve is not None else None
    removed = 0
    for path in candidates[CONFIG_BACKUP_RETENTION:]:
        if protected is not None and path.resolve() == protected:
            continue
        with contextlib.suppress(OSError):
            path.unlink()
            removed += 1
    return removed


def atomic_config_update(plugin: str, changes: dict[str, Any]) -> dict[str, Any]:
    import yaml

    path = hermes_home() / "config.yaml"
    document = read_yaml()
    clean = (
        validate_memory_changes(changes)
        if plugin == "memory"
        else validate_agency_changes(changes)
    )
    key = MEMORY_KEY if plugin == "memory" else AGENCY_KEY
    current = plugin_config(document, key)
    current.update(clean)
    plugins = document.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        raise ValueError("Hermes plugins config must be a mapping")
    plugins[key] = current
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = control_dir() / "config-backups" / f"config-{stamp}.yaml"
    secure_directory(backup.parent)
    shutil.copy2(path, backup)
    with contextlib.suppress(OSError):
        backup.chmod(0o600)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            yaml.safe_dump(document, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
        with contextlib.suppress(OSError):
            path.chmod(0o600)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    pruned = prune_config_backups(preserve=backup)
    return {
        "plugin": plugin,
        "changed": clean,
        "backup": str(backup),
        "restart_required": True,
        "pruned_config_backups": pruned,
    }


def atomic_lab_profile_update(
    memory_changes: dict[str, Any], agency_changes: dict[str, Any]
) -> dict[str, Any]:
    """Validate and commit a cross-plugin policy profile in one config replace."""
    import yaml

    clean_memory = validate_memory_changes(memory_changes)
    clean_agency = validate_agency_changes(agency_changes)
    path = hermes_home() / "config.yaml"
    document = read_yaml()
    plugins = document.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        raise ValueError("Hermes plugins config must be a mapping")
    memory_current = plugin_config(document, MEMORY_KEY)
    agency_current = plugin_config(document, AGENCY_KEY)
    memory_current.update(clean_memory)
    agency_current.update(clean_agency)
    plugins[MEMORY_KEY] = memory_current
    plugins[AGENCY_KEY] = agency_current
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = control_dir() / "config-backups" / f"config-{stamp}.yaml"
    secure_directory(backup.parent)
    shutil.copy2(path, backup)
    with contextlib.suppress(OSError):
        backup.chmod(0o600)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            yaml.safe_dump(document, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
        with contextlib.suppress(OSError):
            path.chmod(0o600)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    pruned = prune_config_backups(preserve=backup)
    return {
        "memory": {"changed": clean_memory},
        "agency": {"changed": clean_agency},
        "backup": str(backup),
        "restart_required": True,
        "pruned_config_backups": pruned,
    }


def restore_internal_config_backup(backup: Path) -> None:
    root = (control_dir() / "config-backups").resolve()
    source = backup.resolve()
    if root not in source.parents or not source.is_file():
        raise RuntimeError(
            "Config rollback source is outside the controller backup directory"
        )
    destination = hermes_home() / "config.yaml"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
        temporary = None
        with contextlib.suppress(OSError):
            destination.chmod(0o600)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def gateway_is_running() -> bool:
    executable = hermes_home() / "hermes-agent" / "venv" / "bin" / "hermes"
    if not executable.is_file():
        executable = Path.home() / ".local" / "bin" / "hermes"
    completed = subprocess.run(
        [str(executable), "gateway", "status"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        env={**os.environ, "HERMES_HOME": str(hermes_home())},
    )
    output = (completed.stdout or completed.stderr or "").lower()
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            (completed.stdout or completed.stderr or "Gateway status failed").strip()
        )
    stopped_markers = ("not running", "stopped", "inactive", "no gateway")
    return completed.returncode == 0 and not any(
        marker in output for marker in stopped_markers
    )


def gateway_main_pid() -> int:
    completed = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            "hermes-gateway.service",
            "--property",
            "MainPID",
            "--value",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
        env={**os.environ, "HERMES_HOME": str(hermes_home())},
    )
    if completed.returncode != 0:
        return 0
    try:
        return max(0, int(completed.stdout.strip() or 0))
    except ValueError:
        return 0


def restart_gateway_if_running(was_running: bool | None = None) -> dict[str, Any]:
    preserve_running = gateway_is_running() if was_running is None else was_running
    if not preserve_running:
        return {"status": "preserved_stopped"}
    action = "restart" if gateway_is_running() else "start"
    activated = hermes_command("gateway", action, timeout=90)
    return {
        "status": "restarted" if action == "restart" else "restored_running",
        "output": activated["output"],
    }


def validate_plugin_health(plugin: str) -> dict[str, Any]:
    if plugin == "memory":
        return hermes_command("consolidating_local", "doctor", timeout=90)
    if plugin == "agency":
        status = hermes_command("conscious-agency", "status", timeout=60)
        heartbeat = hermes_command("conscious-agency", "heartbeat-status", timeout=60)
        return {"status": status, "heartbeat": heartbeat}
    raise ValueError("Unsupported plugin health check")


def apply_lab_profile_transaction(
    memory_changes: dict[str, Any], agency_changes: dict[str, Any]
) -> dict[str, Any]:
    """Update policy and activate the gateway-native heartbeat, with rollback."""

    profile = atomic_lab_profile_update(memory_changes, agency_changes)
    backup = Path(profile["backup"])
    gateway_was_running = gateway_is_running()
    try:
        gateway = restart_gateway_if_running(gateway_was_running)
        health = {
            "memory": validate_plugin_health("memory"),
            "agency": validate_plugin_health("agency"),
        }
    except Exception as apply_error:
        rollback_errors: list[str] = []
        try:
            restore_internal_config_backup(backup)
        except Exception as exc:
            rollback_errors.append(f"config rollback failed: {exc}")
        try:
            restart_gateway_if_running(gateway_was_running)
        except Exception as exc:
            rollback_errors.append(f"gateway rollback failed: {exc}")
        for plugin in ("memory", "agency"):
            try:
                validate_plugin_health(plugin)
            except Exception as exc:
                rollback_errors.append(f"{plugin} rollback health failed: {exc}")
        detail = (
            f"Educational profile activation failed and was rolled back: {apply_error}"
        )
        if rollback_errors:
            detail += "; " + "; ".join(rollback_errors)
        raise RuntimeError(detail) from apply_error
    return {
        **profile,
        "gateway": gateway,
        "health": health,
        "restart_required": False,
    }


def activate_agency_config_update(result: dict[str, Any]) -> dict[str, Any]:
    """Make heartbeat/runtime-sensitive Agency settings effective with rollback."""

    backup = Path(result["backup"])
    gateway_was_running = gateway_is_running()
    try:
        gateway = restart_gateway_if_running(gateway_was_running)
        health = validate_plugin_health("agency")
    except Exception as apply_error:
        rollback_errors: list[str] = []
        try:
            restore_internal_config_backup(backup)
        except Exception as exc:
            rollback_errors.append(f"config rollback failed: {exc}")
        for label, action in (
            ("gateway", lambda: restart_gateway_if_running(gateway_was_running)),
            ("agency health", lambda: validate_plugin_health("agency")),
        ):
            try:
                action()
            except Exception as exc:
                rollback_errors.append(f"{label} rollback failed: {exc}")
        detail = (
            f"Agency configuration activation failed and was rolled back: {apply_error}"
        )
        if rollback_errors:
            detail += "; " + "; ".join(rollback_errors)
        raise RuntimeError(detail) from apply_error
    return {
        **result,
        "gateway": gateway,
        "health": health,
        "restart_required": False,
    }


def activate_memory_config_update(result: dict[str, Any]) -> dict[str, Any]:
    """Make Memory settings effective and roll back config on failed activation."""

    backup = Path(result["backup"])
    gateway_was_running = gateway_is_running()
    try:
        gateway = restart_gateway_if_running(gateway_was_running)
        health = validate_plugin_health("memory")
    except Exception as apply_error:
        rollback_errors: list[str] = []
        try:
            restore_internal_config_backup(backup)
        except Exception as exc:
            rollback_errors.append(f"config rollback failed: {exc}")
        try:
            restart_gateway_if_running(gateway_was_running)
        except Exception as exc:
            rollback_errors.append(f"gateway rollback failed: {exc}")
        try:
            validate_plugin_health("memory")
        except Exception as exc:
            rollback_errors.append(f"memory rollback health failed: {exc}")
        detail = (
            f"Memory configuration activation failed and was rolled back: {apply_error}"
        )
        if rollback_errors:
            detail += "; " + "; ".join(rollback_errors)
        raise RuntimeError(detail) from apply_error
    return {
        **result,
        "gateway": gateway,
        "health": health,
        "restart_required": False,
    }


def backup_path(kind: str, database: str = "base") -> Path:
    if kind not in {"memory", "agency"}:
        raise ValueError("Unsupported backup kind")
    if kind == "memory" and database != "base" and not SCOPE_ID.fullmatch(database):
        raise ValueError("Unknown memory database ID")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    suffix = f"-{database}" if kind == "memory" else ""
    root = secure_directory(control_dir() / "backups")
    path = root / kind / f"{kind}-{stamp}{suffix}.db"
    secure_directory(path.parent)
    return path


def backup_manifest_path(database_path: Path) -> Path:
    return Path(str(database_path) + ".manifest.json")


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    secure_directory(path.parent)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
        with contextlib.suppress(OSError):
            path.chmod(0o600)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def schema_identity(connection: Any) -> dict[str, Any]:
    version_row = connection.execute("PRAGMA user_version").fetchone()
    tables = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    canonical = "\n".join(tables)
    return {
        "user_version": int(version_row[0] if version_row else 0),
        "table_count": len(tables),
        "tables_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def write_backup_manifest(
    path: Path,
    *,
    kind: str,
    database: str,
    plugin_version: str,
    encrypted: bool,
    schema: dict[str, Any],
    automatic: bool = False,
) -> dict[str, Any]:
    value = {
        "format": 1,
        "kind": kind,
        "database": database,
        "plugin_version": plugin_version,
        "encrypted": encrypted,
        "automatic": automatic,
        "schema": schema,
        "created_at": now_iso(),
        "backup_sha256": file_fingerprint(path)["sha256"],
    }
    write_json_atomic(backup_manifest_path(path), value)
    return value


def prune_automatic_backups(*, kind: str, database: str) -> int:
    """Retain recent rollback backups and preserve every manual/legacy file."""

    if kind not in {"memory", "agency"}:
        raise ValueError("Invalid backup kind")
    directory = control_dir() / "backups" / kind
    if not directory.is_dir():
        return 0
    candidates: list[Path] = []
    for path in directory.glob("*.db"):
        sidecar = backup_manifest_path(path)
        if not sidecar.is_file():
            continue
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(metadata, dict)
            and metadata.get("format") == 1
            and metadata.get("kind") == kind
            and metadata.get("database") == database
            and metadata.get("automatic") is True
        ):
            candidates.append(path)
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    removed = 0
    for path in candidates[AUTOMATIC_BACKUPS_PER_TARGET:]:
        sidecar = backup_manifest_path(path)
        try:
            path.unlink()
            sidecar.unlink(missing_ok=True)
            removed += 1
        except OSError:
            # A partially failed pair deletion remains visible/diagnosable. A
            # later pass can finish it; never touch unrelated files.
            continue
    return removed


def backup_manifest_shape_valid(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("format") != 1:
        return False
    schema = value.get("schema")
    if (
        value.get("kind") not in {"memory", "agency"}
        or not isinstance(value.get("database"), str)
        or not value["database"]
        or not isinstance(value.get("plugin_version"), str)
        or not value["plugin_version"]
        or type(value.get("encrypted")) is not bool
        or type(value.get("automatic", False)) is not bool
        or not isinstance(schema, dict)
        or type(schema.get("user_version")) is not int
        or type(schema.get("table_count")) is not int
        or not re.fullmatch(r"[a-f0-9]{64}", str(schema.get("tables_sha256") or ""))
        or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("backup_sha256") or ""))
    ):
        return False
    try:
        created = datetime.fromisoformat(str(value.get("created_at") or ""))
    except ValueError:
        return False
    return created.tzinfo is not None


def verify_backup_manifest(
    path: Path, *, kind: str, database: str, encrypted: bool
) -> dict[str, Any]:
    sidecar = backup_manifest_path(path)
    if not sidecar.is_file():
        # Backups produced before manifest support remain recoverable, but are
        # explicitly identified as legacy and still receive integrity checks
        # during restore. Filename binding prevents cross-scope restoration.
        expected_suffix = f"-{database}.db" if kind == "memory" else ".db"
        if kind == "memory" and not path.name.endswith(expected_suffix):
            raise RuntimeError(
                "Legacy memory backup does not match the target database"
            )
        return {
            "legacy": True,
            "verified": False,
            "backup_sha256": file_fingerprint(path).get("sha256", ""),
        }
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Backup manifest is unreadable") from exc
    if not backup_manifest_shape_valid(value):
        raise RuntimeError("Backup manifest structure is invalid")
    if value.get("kind") != kind or value.get("database") != database:
        raise RuntimeError("Backup manifest does not match the restore target")
    if value["encrypted"] is not encrypted:
        raise RuntimeError("Backup encryption mode does not match the active store")
    actual_digest = file_fingerprint(path).get("sha256", "")
    if not actual_digest or not hmac.compare_digest(
        str(value.get("backup_sha256") or ""), actual_digest
    ):
        raise RuntimeError("Backup digest does not match its manifest")
    return {**value, "legacy": False, "verified": True}


def memory_backup(payload: dict[str, Any], automatic: bool = False) -> dict[str, Any]:
    database = str(payload.get("database") or "base")
    # Resolve the opaque database ID before creating any path. This prevents a
    # crafted ID from influencing backup directory creation.
    selected_memory_path(payload)
    target = backup_path("memory", database)
    with memory_store(payload) as store:
        schema = schema_identity(store._conn)
        result = store.backup_to(target)
    config = plugin_config(read_yaml(), MEMORY_KEY)
    backup = Path(result)
    backup_manifest = write_backup_manifest(
        backup,
        kind="memory",
        database=database,
        plugin_version=str(manifest(memory_module_path()).get("version") or "unknown"),
        encrypted=config_bool(config.get("database_encryption")),
        schema=schema,
        automatic=automatic,
    )
    pruned = prune_automatic_backups(kind="memory", database=database)
    return {
        "kind": "memory",
        "id": Path(result).name,
        "path": result,
        "automatic": automatic,
        "manifest_verified": backup_manifest["backup_sha256"]
        == file_fingerprint(backup).get("sha256"),
        "pruned_automatic_backups": pruned,
    }


def agency_backup(automatic: bool = False) -> dict[str, Any]:
    _, config, _, store = agency_objects()
    target = backup_path("agency")
    temporary = None
    destination = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, suffix=".db", delete=False
        ) as handle:
            temporary = Path(handle.name)
        with store.connection() as source:
            schema = schema_identity(source)
            destination = store._driver.connect(str(temporary), timeout=10.0)
            if config.database_encryption:
                secret = os.environ[config.database_key_env].encode("utf-8")
                raw_key = hashlib.sha256(secret).hexdigest()
                destination.execute(f"PRAGMA key = \"x'{raw_key}'\"")
            source.backup(destination)
            destination.commit()
            integrity = destination.execute("PRAGMA integrity_check").fetchone()
            if not integrity or str(integrity[0]) != "ok":
                raise RuntimeError(f"Agency backup integrity check failed: {integrity}")
            destination.close()
            destination = None
        os.replace(temporary, target)
        temporary = None
        with contextlib.suppress(OSError):
            target.chmod(0o600)
    finally:
        if destination is not None:
            destination.close()
        if temporary and temporary.exists():
            temporary.unlink()
    backup_manifest = write_backup_manifest(
        target,
        kind="agency",
        database="agency",
        plugin_version=str(manifest(agency_module_path()).get("version") or "unknown"),
        encrypted=config.database_encryption is True,
        schema=schema,
        automatic=automatic,
    )
    pruned = prune_automatic_backups(kind="agency", database="agency")
    return {
        "kind": "agency",
        "id": target.name,
        "path": str(target),
        "automatic": automatic,
        "manifest_verified": backup_manifest["backup_sha256"]
        == file_fingerprint(target).get("sha256"),
        "pruned_automatic_backups": pruned,
    }


def apply_agency_key(connection: Any, config: Any) -> None:
    if not config.database_encryption:
        return
    secret = os.environ.get(config.database_key_env, "")
    if not secret:
        raise RuntimeError(
            f"Agency encryption key {config.database_key_env} is not loaded"
        )
    raw_key = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    connection.execute(f"PRAGMA key = \"x'{raw_key}'\"")


def restore_agency(source: Path) -> dict[str, Any]:
    _, config, _, store = agency_objects()
    destination_path = config.db_path
    temporary = None
    source_connection = None
    destination_connection = None
    held_sidecars: list[tuple[Path, Path]] = []
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination_path.parent, suffix=".db", delete=False
        ) as handle:
            temporary = Path(handle.name)
        source_connection = store._driver.connect(str(source), timeout=10.0)
        destination_connection = store._driver.connect(str(temporary), timeout=10.0)
        apply_agency_key(source_connection, config)
        apply_agency_key(destination_connection, config)
        integrity = source_connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]) != "ok":
            raise RuntimeError(
                f"Agency source backup failed integrity check: {integrity}"
            )
        source_connection.backup(destination_connection)
        destination_connection.commit()
        restored = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if not restored or str(restored[0]) != "ok":
            raise RuntimeError(
                f"Restored agency database failed integrity check: {restored}"
            )
        source_connection.close()
        source_connection = None
        destination_connection.close()
        destination_connection = None
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(destination_path) + suffix)
            if sidecar.exists():
                held = Path(str(temporary) + suffix + ".old")
                os.replace(sidecar, held)
                held_sidecars.append((sidecar, held))
        try:
            os.replace(temporary, destination_path)
            temporary = None
        except Exception:
            for sidecar, held in reversed(held_sidecars):
                if held.exists():
                    os.replace(held, sidecar)
            held_sidecars.clear()
            raise
        for _, held in held_sidecars:
            with contextlib.suppress(OSError):
                held.unlink()
        held_sidecars.clear()
        with contextlib.suppress(OSError):
            destination_path.chmod(0o600)
        return {"restored_from": str(source), "database": str(destination_path)}
    finally:
        if source_connection is not None:
            source_connection.close()
        if destination_connection is not None:
            destination_connection.close()
        if temporary and temporary.exists():
            temporary.unlink()
        for _, held in held_sidecars:
            with contextlib.suppress(OSError):
                held.unlink()


def memory_restore_health(payload: dict[str, Any]) -> dict[str, Any]:
    with memory_store(payload) as store:
        report = store.doctor(repair=False)
    integrity = report.get("integrity") if isinstance(report, dict) else None
    structurally_healthy = (
        isinstance(report, dict)
        and integrity == ["ok"]
        and not report.get("fts_mismatches")
        and not any((report.get("dangling_references") or {}).values())
    )
    if not structurally_healthy:
        raise RuntimeError(f"Restored memory database failed doctor: {integrity}")
    return {
        "ok": True,
        "integrity": integrity,
        "failed_operations": int(report.get("failed_operations") or 0),
    }


def agency_restore_health() -> dict[str, Any]:
    _, _, engine, store = agency_objects()
    with store.connection() as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if not integrity or str(integrity[0]) != "ok":
        raise RuntimeError(
            f"Restored agency database failed integrity check: {integrity}"
        )
    snapshot = engine.snapshot()
    if not isinstance(snapshot, dict) or "runtime" not in snapshot:
        raise RuntimeError(
            "Restored agency database could not produce a runtime snapshot"
        )
    return {"ok": True, "integrity": "ok"}


def backup_inventory() -> list[dict[str, Any]]:
    root = control_dir() / "backups"
    result = []
    if root.is_dir():
        for kind in ("memory", "agency"):
            directory = root / kind
            if not directory.is_dir():
                continue
            for path in sorted(
                directory.glob("*.db"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )[:100]:
                manifest_status: dict[str, Any] = {
                    "manifest": False,
                    "verified": False,
                    "legacy": True,
                }
                sidecar = backup_manifest_path(path)
                if sidecar.is_file():
                    try:
                        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
                        if not isinstance(metadata, dict):
                            raise ValueError("manifest root must be an object")
                        actual_digest = file_fingerprint(path).get("sha256", "")
                        manifest_status = {
                            "manifest": True,
                            "verified": (
                                backup_manifest_shape_valid(metadata)
                                and metadata.get("kind") == kind
                                and bool(actual_digest)
                                and hmac.compare_digest(
                                    str(metadata.get("backup_sha256") or ""),
                                    actual_digest,
                                )
                            ),
                            "legacy": False,
                            "database": str(metadata.get("database") or ""),
                            "automatic": metadata.get("automatic") is True,
                            "encrypted": metadata.get("encrypted")
                            if type(metadata.get("encrypted")) is bool
                            else None,
                            "plugin_version": str(
                                metadata.get("plugin_version") or "unknown"
                            ),
                        }
                    except (OSError, ValueError, json.JSONDecodeError):
                        manifest_status = {
                            "manifest": True,
                            "verified": False,
                            "legacy": False,
                        }
                result.append(
                    {
                        "id": path.name,
                        "kind": kind,
                        "size": path.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            path.stat().st_mtime, UTC
                        ).isoformat(),
                        **manifest_status,
                    }
                )
    return result


def resolve_backup(kind: str, backup_id: str) -> Path:
    if kind not in {"memory", "agency"}:
        raise ValueError("Invalid backup kind")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}\.db", backup_id):
        raise ValueError("Invalid backup ID")
    root = (control_dir() / "backups" / kind).resolve()
    path = (root / backup_id).resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError("Controller backup not found")
    return path


def validate_mutation_preflight(operation: str, payload: dict[str, Any]) -> None:
    if operation not in MUTATION_OPERATIONS:
        raise ValueError("Unsupported mutation")
    unexpected = sorted(set(payload) - MUTATION_PAYLOAD_FIELDS[operation])
    if unexpected:
        raise ValueError(
            f"Unsupported payload field for {operation}: {', '.join(unexpected)}"
        )
    if operation.startswith("memory_"):
        selected_memory_path(payload)
    if operation == "memory_export":
        strict_bool(payload, "include_sensitive")
    if operation == "memory_resolve_approval":
        strict_bool(payload, "approved", required=True)
    if operation == "memory_update_item":
        logical = str(payload.get("table") or "")
        if logical not in MEMORY_EDIT_FIELDS:
            raise ValueError("This memory ledger is not operator-editable")
        if logical == "sessions":
            if not str(payload.get("id") or "").strip():
                raise ValueError("id must identify a memory session")
        else:
            strict_positive_int(payload, "id")
        if not isinstance(payload.get("changes"), dict) or not payload["changes"]:
            raise ValueError("At least one memory field change is required")
        table = MEMORY_TABLES[logical]
        id_field = "session_id" if logical == "sessions" else "id"
        row_id = (
            str(payload.get("id") or "").strip()
            if id_field == "session_id"
            else strict_positive_int(payload, "id")
        )
        with memory_store(payload, read_only=True) as store:
            columns = table_columns_memory(store, table)
            current = store._fetchone(
                f"SELECT * FROM {table} WHERE {id_field} = ?", (row_id,)
            )
            if not current:
                raise ValueError("The selected memory item no longer exists")
            clean = validate_memory_patch(logical, payload["changes"], current)
            if not set(clean).issubset(columns):
                raise ValueError(
                    "The installed plugin schema does not support one of these fields"
                )
    if operation in {
        "memory_deactivate_fact",
        "memory_resolve_approval",
        "memory_resolve_intention",
    }:
        row_id = strict_positive_int(payload, "id")
        table, condition = {
            "memory_deactivate_fact": ("facts", "active=1"),
            "memory_resolve_approval": ("memory_approvals", "status='pending'"),
            "memory_resolve_intention": ("prospective_memories", "1=1"),
        }[operation]
        with memory_store(payload, read_only=True) as store:
            if not store._fetchone(
                f"SELECT id FROM {table} WHERE id=? AND {condition}", (row_id,)
            ):
                raise ValueError("The selected memory item is no longer actionable")
    if operation == "memory_restore":
        resolve_backup("memory", str(payload.get("backup_id") or ""))
    elif operation == "agency_restore":
        resolve_backup("agency", str(payload.get("backup_id") or ""))
    elif operation == "config_apply":
        plugin = str(payload.get("plugin") or "")
        changes = payload.get("changes")
        if plugin not in {"memory", "agency"} or not isinstance(changes, dict):
            raise ValueError("Config apply requires a plugin and changes mapping")
        if not changes:
            raise ValueError("At least one configuration change is required")
        if plugin == "memory":
            validate_memory_changes(changes)
        else:
            validate_agency_changes(changes)
    elif operation == "lab_apply_profile" and payload.get("profile") not in {
        "recommended",
        "unrestricted_research",
    }:
        raise ValueError("Unknown Educational Lab profile")
    if operation == "agency_add_intention":
        title = str(payload.get("title") or "").strip()
        if not title or len(title) > 500:
            raise ValueError("title must be non-empty and at most 500 characters")
        priority = payload.get("priority", 50)
        if type(priority) is not int or not 0 <= priority <= 100:
            raise ValueError("priority must be an integer between 0 and 100")
        if payload.get("autonomy", "propose") not in {"reflect", "propose", "message"}:
            raise ValueError("Invalid autonomy")
        if payload.get("due_at") is not None and str(payload.get("due_at")).strip():
            _, _, _, store = agency_objects(read_only=True)
            store._normalize_due_at(payload["due_at"])
    if operation == "agency_update_intention":
        intention_id = str(payload.get("id") or "").strip()
        if not intention_id:
            raise ValueError("An intention ID is required")
        status = payload.get("status")
        if status not in {None, "active", "blocked", "completed", "cancelled"}:
            raise ValueError("Invalid status")
        if "priority" in payload and (
            type(payload["priority"]) is not int or not 0 <= payload["priority"] <= 100
        ):
            raise ValueError("priority must be an integer between 0 and 100")
        _, _, _, store = agency_objects(read_only=True)
        if store.get_intention(intention_id) is None:
            raise ValueError("The selected agency intention no longer exists")
        if payload.get("due_at") is not None and str(payload.get("due_at")).strip():
            store._normalize_due_at(payload["due_at"])
    for agency_action, field, maximum in (
        ("agency_focus", "focus", 1000),
        ("agency_add_question", "question", 1000),
        ("agency_add_observation", "observation", 2000),
    ):
        if operation == agency_action:
            value = str(payload.get(field) or "").strip()
            if not value or len(value) > maximum:
                raise ValueError(
                    f"{field} must be non-empty and at most {maximum} characters"
                )
    if operation == "agency_resolve_question":
        question_id = str(payload.get("id") or "").strip()
        if not question_id:
            raise ValueError("A question ID is required")
        _, _, engine, _ = agency_objects(read_only=True)
        questions = engine.snapshot().get("workspace", {}).get("questions", [])
        if question_id not in {
            str(item.get("id") or "") for item in questions if isinstance(item, dict)
        }:
            raise ValueError("The selected agency question no longer exists")


def mutation_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    operation = str(payload.get("action") or "")
    action_payload = payload.get("payload")
    if not isinstance(action_payload, dict):
        raise ValueError("Preflight payload must contain an action payload mapping")
    validate_mutation_preflight(operation, action_payload)
    payload_canonical = json.dumps(
        action_payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    state: dict[str, Any] = {
        "operation": operation,
        "payload": audit_safe(action_payload),
        "payload_sha256": hashlib.sha256(
            payload_canonical.encode("utf-8")
        ).hexdigest(),
        "config": file_fingerprint(hermes_home() / "config.yaml"),
        "control_bridge": file_fingerprint(Path(__file__).resolve()),
        "memory_source": plugin_source_fingerprint(memory_module_path()),
        "agency_source": plugin_source_fingerprint(agency_module_path()),
    }
    if operation.startswith("memory_"):
        state["memory"] = database_fingerprint(selected_memory_path(action_payload))
    if operation.startswith("agency_"):
        _, load_config, _, _ = import_agency()
        agency_path = Path(load_config().db_path).expanduser().resolve()
        state["agency"] = database_fingerprint(agency_path)
    if operation == "memory_restore":
        state["restore_source"] = file_fingerprint(
            resolve_backup("memory", str(action_payload.get("backup_id") or ""))
        )
    elif operation == "agency_restore":
        state["restore_source"] = file_fingerprint(
            resolve_backup("agency", str(action_payload.get("backup_id") or ""))
        )
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return {
        "token": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "validated_at": now_iso(),
    }


def hermes_command(*args: str, timeout: int = 45) -> dict[str, Any]:
    executable = hermes_home() / "hermes-agent" / "venv" / "bin" / "hermes"
    if not executable.is_file():
        executable = Path.home() / ".local" / "bin" / "hermes"
    completed = subprocess.run(
        [str(executable), *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env={**os.environ, "HERMES_HOME": str(hermes_home())},
    )
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        raise RuntimeError(output or f"Hermes command failed: {' '.join(args)}")
    return {"command": list(args), "output": output[-8000:]}


@contextlib.contextmanager
def quiesced_gateway():
    """Stop a running gateway for restore and preserve its prior run state."""
    executable = hermes_home() / "hermes-agent" / "venv" / "bin" / "hermes"
    if not executable.is_file():
        executable = Path.home() / ".local" / "bin" / "hermes"
    status = subprocess.run(
        [str(executable), "gateway", "status"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        env={**os.environ, "HERMES_HOME": str(hermes_home())},
    )
    output = (status.stdout or status.stderr or "").lower()
    if status.returncode not in {0, 1}:
        raise RuntimeError(
            (status.stdout or status.stderr or "Gateway status failed").strip()
        )
    stopped_markers = ("not running", "stopped", "inactive", "no gateway")
    was_running = status.returncode == 0 and not any(
        marker in output for marker in stopped_markers
    )
    if was_running:
        hermes_command("gateway", "stop", timeout=45)
    try:
        yield {"was_running": was_running}
    except Exception as operation_error:
        if was_running:
            try:
                hermes_command("gateway", "start", timeout=60)
            except Exception as restart_error:
                raise RuntimeError(
                    f"{operation_error}; gateway restart also failed: {restart_error}"
                ) from operation_error
        raise
    else:
        if was_running:
            hermes_command("gateway", "start", timeout=60)


@contextlib.contextmanager
def mutation_lock():
    """Allow only one state-changing Control bridge process at a time."""

    if not _MUTATION_THREAD_LOCK.acquire(blocking=False):
        raise RuntimeError("Another Control Center mutation is already in progress")
    path = control_dir() / "mutation.lock"
    secure_directory(path.parent)
    handle = None
    locked = False
    try:
        handle = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except (OSError, BlockingIOError) as exc:
            raise RuntimeError(
                "Another Control Center mutation is already in progress"
            ) from exc
        with contextlib.suppress(OSError):
            path.chmod(0o600)
        yield
    finally:
        if handle is not None:
            if locked:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    with contextlib.suppress(OSError):
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    with contextlib.suppress(OSError):
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        _MUTATION_THREAD_LOCK.release()


def audit_path() -> Path:
    return control_dir() / "audit.jsonl"


@contextlib.contextmanager
def locked_audit_file(path: Path, mode: str, *, exclusive: bool):
    """Lock the audit stream across bridge processes on WSL."""

    with _AUDIT_THREAD_LOCK, path.open(mode, encoding="utf-8") as handle:
        flock = None
        try:
            if os.name != "nt":
                import fcntl

                flock = fcntl
                flock.flock(
                    handle.fileno(), flock.LOCK_EX if exclusive else flock.LOCK_SH
                )
            yield handle
        finally:
            if flock is not None:
                with contextlib.suppress(OSError):
                    flock.flock(handle.fileno(), flock.LOCK_UN)


def audit_safe(value: Any, key: str = "", depth: int = 0) -> Any:
    """Keep proofs and routing metadata without duplicating private memory text."""
    lowered = key.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return "<redacted>"
    if depth > 8:
        return "<depth-limit>"
    if isinstance(value, str):
        if lowered in AUDIT_TEXT_FIELDS:
            return {
                "text_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                "chars": len(value),
            }
        return value if len(value) <= 1000 else value[:1000] + "…"
    if isinstance(value, dict):
        return {
            str(item_key): audit_safe(item, str(item_key), depth + 1)
            for item_key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple)):
        return [audit_safe(item, key, depth + 1) for item in list(value)[:100]]
    if value is None or type(value) in {bool, int, float}:
        return value
    return str(value)[:1000]


def append_audit(
    operation: str, payload: dict[str, Any], result: Any, backup: Any = None
) -> dict[str, Any]:
    path = audit_path()
    secure_directory(path.parent)
    previous = "0" * 64
    with locked_audit_file(path, "a+", exclusive=True) as handle:
        handle.seek(0)
        for line in handle:
            if line.strip():
                try:
                    previous = str(json.loads(line)["hash"])
                except Exception:
                    previous = "invalid"
        event = {
            "id": uuid.uuid4().hex,
            "at": now_iso(),
            "operation": operation,
            "payload": audit_safe(payload),
            "result": audit_safe(result),
            "backup": audit_safe(backup),
            "previous_hash": previous,
        }
        canonical = json.dumps(
            event, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        event["hash"] = hashlib.sha256(
            (previous + canonical).encode("utf-8")
        ).hexdigest()
        handle.seek(0, os.SEEK_END)
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return {"id": event["id"], "hash": event["hash"]}


def read_audit(payload: dict[str, Any]) -> dict[str, Any]:
    path = audit_path()
    if not path.is_file():
        return {"valid": True, "events": []}
    previous = "0" * 64
    valid = True
    limit = safe_limit(payload, 100)
    rows: list[dict[str, Any]] = []
    with locked_audit_file(path, "r", exclusive=False) as handle:
        for raw in handle:
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
                claimed = event.pop("hash")
                canonical = json.dumps(
                    event, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                actual = hashlib.sha256(
                    (previous + canonical).encode("utf-8")
                ).hexdigest()
                valid = (
                    valid
                    and event.get("previous_hash") == previous
                    and claimed == actual
                )
                previous = claimed
                event["hash"] = claimed
                rows.append(event)
                if len(rows) > limit:
                    rows.pop(0)
            except Exception:
                valid = False
    return {"valid": valid, "events": list(reversed(rows))}


def wiki_root() -> Path:
    config = plugin_config(read_yaml(), MEMORY_KEY)
    raw = str(config.get("wiki_export_dir") or "$HERMES_HOME/consolidating_memory_wiki")
    path = Path(raw.replace("$HERMES_HOME", str(hermes_home()))).expanduser().resolve()
    if hermes_home() not in path.parents:
        raise ValueError("Wiki export directory must be inside HERMES_HOME")
    return path


def wiki_list() -> list[dict[str, Any]]:
    root = wiki_root()
    if not root.is_dir():
        return []
    return [
        {
            "id": path.relative_to(root).as_posix(),
            "title": path.stem.replace("-", " "),
            "size": path.stat().st_size,
        }
        for path in sorted(root.rglob("*.md"))[:500]
        if path.is_file()
    ]


def wiki_read(payload: dict[str, Any]) -> dict[str, Any]:
    identifier = str(payload.get("id") or "")
    if (
        not identifier.endswith(".md")
        or ".." in Path(identifier).parts
        or "\0" in identifier
    ):
        raise ValueError("Invalid wiki page ID")
    root = wiki_root().resolve()
    path = (root / identifier).resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError("Wiki page not found")
    return {"id": identifier, "markdown": path.read_text(encoding="utf-8")[:1_000_000]}


def probe() -> dict[str, Any]:
    document = read_yaml()
    memory_cfg = plugin_config(document, MEMORY_KEY)
    agency_cfg = plugin_config(document, AGENCY_KEY)
    memory_manifest = manifest(memory_module_path())
    agency_manifest = manifest(agency_module_path())
    version = ""
    with contextlib.suppress(Exception):
        version = hermes_command("--version", timeout=20)["output"].splitlines()[0]
    agency = None
    if agency_manifest["installed"]:
        try:
            snapshot = agency_snapshot()
            agency = {
                "healthy": True,
                "paused": snapshot["snapshot"]["runtime"].get("paused", False),
                "gates": snapshot["gates"],
                "contract": contract_audit(),
            }
        except Exception as exc:
            agency = {
                "healthy": False,
                "error": f"{type(exc).__name__}: {exc}",
                "contract": contract_audit(),
            }
    return {
        "home": str(hermes_home()),
        "hermes_version": version,
        "memory": {
            **memory_manifest,
            "config": redact_config(memory_cfg),
            "databases": memory_databases(),
        },
        "agency": {
            **agency_manifest,
            "config": redact_config(agency_cfg),
            "runtime": agency,
        },
        "control": {
            "protocol": PROTOCOL,
            "audit": read_audit({"limit": 1}),
            "backups": len(backup_inventory()),
        },
    }


def _execute_mutation_locked(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    expected_preflight = payload.get("_preflight_token")
    if not isinstance(expected_preflight, str) or not re.fullmatch(
        r"[a-f0-9]{64}", expected_preflight
    ):
        raise ValueError("A valid mutation preflight token is required")
    payload = {
        key: value for key, value in payload.items() if key != "_preflight_token"
    }
    current_preflight = mutation_preflight({"action": operation, "payload": payload})
    if not hmac.compare_digest(expected_preflight, current_preflight["token"]):
        raise RuntimeError(
            "The target state changed after preview; preview the operation again"
        )
    backup = None
    result: Any
    if operation == "memory_backup":
        result = memory_backup(payload)
    elif operation == "agency_backup":
        result = agency_backup()
    elif operation == "agency_restore":
        backup = agency_backup(automatic=True)
        source = resolve_backup("agency", str(payload.get("backup_id") or ""))
        _, agency_config, _, _ = agency_objects()
        verification = verify_backup_manifest(
            source,
            kind="agency",
            database="agency",
            encrypted=agency_config.database_encryption is True,
        )
        with quiesced_gateway():
            try:
                result = restore_agency(source)
                result["health"] = agency_restore_health()
            except Exception as restore_error:
                rollback_error = None
                try:
                    restore_agency(Path(backup["path"]))
                    agency_restore_health()
                except Exception as exc:
                    rollback_error = exc
                detail = (
                    f"Agency restore failed and the previous database was restored: {restore_error}"
                    if rollback_error is None
                    else f"Agency restore failed: {restore_error}; rollback failed: {rollback_error}"
                )
                raise RuntimeError(detail) from restore_error
        result["manifest"] = verification
    elif operation == "memory_export":
        backup = memory_backup(payload, automatic=True)
        target = (
            control_dir()
            / "exports"
            / f"memory-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
        )
        secure_directory(target.parent)
        with memory_store(payload) as store:
            include_sensitive = strict_bool(payload, "include_sensitive")
            data = store.export_data(redact_sensitive=not include_sensitive)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=target.parent, delete=False
            ) as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, target)
            temporary = None
            with contextlib.suppress(OSError):
                target.chmod(0o600)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        result = {
            "path": str(target),
            "sensitive_redacted": not include_sensitive,
        }
    elif operation == "memory_deactivate_fact":
        backup = memory_backup(payload, automatic=True)
        fact_id = strict_positive_int(payload, "id")
        with memory_store(payload) as store:
            result = {
                "id": fact_id,
                "deactivated": store.deactivate_fact(
                    fact_id, reason="operator_control_center", source="control_center"
                ),
            }
    elif operation == "memory_update_item":
        backup = memory_backup(payload, automatic=True)
        result = memory_update_item(payload)
    elif operation == "memory_resolve_approval":
        backup = memory_backup(payload, automatic=True)
        with memory_store(payload) as store:
            result = store.resolve_approval(
                strict_positive_int(payload, "id"),
                approved=strict_bool(payload, "approved", required=True),
                resolution=str(payload.get("resolution") or "Resolved by operator")[
                    :500
                ],
            )
    elif operation == "memory_resolve_intention":
        backup = memory_backup(payload, automatic=True)
        status = str(payload.get("status") or "completed")
        if status not in {"completed", "cancelled", "pending"}:
            raise ValueError("Unsupported prospective-memory status")
        with memory_store(payload) as store:
            result = store.resolve_intention(
                strict_positive_int(payload, "id"), status=status
            )
    elif operation == "memory_retry_failed":
        backup = memory_backup(payload, automatic=True)
        with memory_store(payload) as store:
            result = {
                "retried": store.retry_failed_operations(
                    limit=min(safe_limit(payload), 1000)
                )
            }
    elif operation == "memory_maintain":
        backup = memory_backup(payload, automatic=True)
        with quiesced_gateway():
            with memory_store(payload) as store:
                result = store.maintain()
    elif operation == "memory_restore":
        backup = memory_backup(payload, automatic=True)
        source = resolve_backup("memory", str(payload.get("backup_id") or ""))
        destination = selected_memory_path(payload)
        database = str(payload.get("database") or "base")
        memory_config = plugin_config(read_yaml(), MEMORY_KEY)
        encrypted = config_bool(memory_config.get("database_encryption"))
        verification = verify_backup_manifest(
            source,
            kind="memory",
            database=database,
            encrypted=encrypted,
        )
        with quiesced_gateway():
            from consolidating_local.admin import _restore

            encryption_key = (
                os.environ.get("CONSOLIDATING_MEMORY_DB_KEY", "") if encrypted else ""
            )
            try:
                result = _restore(
                    source,
                    destination,
                    encryption_key=encryption_key,
                )
                result["health"] = memory_restore_health(payload)
            except Exception as restore_error:
                rollback_error = None
                try:
                    _restore(
                        Path(backup["path"]),
                        destination,
                        encryption_key=encryption_key,
                    )
                    memory_restore_health(payload)
                except Exception as exc:
                    rollback_error = exc
                detail = (
                    f"Memory restore failed and the previous database was restored: {restore_error}"
                    if rollback_error is None
                    else f"Memory restore failed: {restore_error}; rollback failed: {rollback_error}"
                )
                raise RuntimeError(detail) from restore_error
        result["manifest"] = verification
    elif operation == "config_apply":
        plugin = str(payload.get("plugin") or "")
        if plugin not in {"memory", "agency"} or not isinstance(
            payload.get("changes"), dict
        ):
            raise ValueError("Config apply requires a plugin and changes mapping")
        result = atomic_config_update(plugin, payload["changes"])
        if plugin == "agency":
            result = activate_agency_config_update(result)
        else:
            result = activate_memory_config_update(result)
        backup = {"path": result["backup"], "kind": "config"}
    elif operation == "agency_pause":
        backup = agency_backup(automatic=True)
        _, _, engine, _ = agency_objects()
        result = engine.pause(str(payload.get("reason") or "Paused by operator")[:500])
    elif operation == "agency_resume":
        backup = agency_backup(automatic=True)
        _, _, engine, _ = agency_objects()
        result = engine.resume_by_user()
    elif operation == "agency_focus":
        backup = agency_backup(automatic=True)
        _, _, engine, _ = agency_objects()
        result = engine.set_focus(
            str(payload.get("focus") or "")[:1000],
            str(payload.get("reason") or "")[:1000],
        )
    elif operation == "agency_add_intention":
        backup = agency_backup(automatic=True)
        _, _, _, store = agency_objects()
        autonomy = str(payload.get("autonomy") or "propose")
        if autonomy not in {"reflect", "propose", "message"}:
            raise ValueError("Invalid autonomy")
        result = store.add_intention(
            str(payload.get("title") or "")[:500],
            rationale=str(payload.get("rationale") or "")[:2000],
            priority=max(0, min(int(payload.get("priority", 50)), 100)),
            autonomy=autonomy,
            due_at=payload.get("due_at"),
            source="operator_control_center",
        )
    elif operation == "agency_add_question":
        backup = agency_backup(automatic=True)
        _, _, engine, _ = agency_objects()
        result = engine.add_question(
            str(payload.get("question") or "")[:1000], source="operator_control_center"
        )
    elif operation == "agency_resolve_question":
        backup = agency_backup(automatic=True)
        _, _, engine, _ = agency_objects()
        question_id = str(payload.get("id") or "")[:100]
        result = {"id": question_id, "resolved": engine.resolve_question(question_id)}
    elif operation == "agency_add_observation":
        backup = agency_backup(automatic=True)
        _, _, engine, _ = agency_objects()
        result = engine.add_self_observation(
            str(payload.get("observation") or "")[:2000]
        )
    elif operation == "agency_update_intention":
        backup = agency_backup(automatic=True)
        _, _, _, store = agency_objects()
        status = payload.get("status")
        if status not in {None, "active", "blocked", "completed", "cancelled"}:
            raise ValueError("Invalid status")
        priority = payload.get("priority")
        result = store.update_intention(
            str(payload.get("id") or ""),
            status=status,
            priority=None if priority is None else int(priority),
            due_at=payload.get("due_at") if "due_at" in payload else None,
        )
    elif operation == "agency_heartbeat_run":
        import_agency()
        from agency.heartbeat import request_heartbeat_wake

        result = {
            "request_id": request_heartbeat_wake("manual", "Control Center operator"),
            "status": "queued",
        }
    elif operation in {"agency_heartbeat_enable", "agency_heartbeat_disable"}:
        enabled = operation.endswith("_enable")
        result = atomic_config_update("agency", {"heartbeat_enabled": enabled})
        result = activate_agency_config_update(result)
        backup = {"path": result["backup"], "kind": "config"}
    elif operation == "agency_migrate_heartbeat":
        backup = agency_backup(automatic=True)
        import_agency()
        from agency.heartbeat import remove_legacy_cron

        result = remove_legacy_cron()
    elif operation == "gateway_restart":
        result = hermes_command("gateway", "restart", timeout=90)
    elif operation == "lab_apply_profile":
        profile = str(payload.get("profile") or "")
        if profile == "unrestricted_research":
            memory_changes = {
                "sensitive_memory": "allow",
                "allow_credential_memory": True,
                "allow_sensitive_model_processing": True,
                "export_redact_sensitive": False,
            }
            agency_changes = {
                "heartbeat_enabled": True,
                "allow_proactive_messages": True,
                "require_prior_user_interaction": False,
                "store_transcript_excerpts": True,
                "minimum_user_silence_hours": 0,
                "cooldown_hours": 0,
                "daily_message_limit": 100,
                "maximum_message_chars": 4000,
                "maximum_reflections_per_tick": 5,
                "maximum_state_changes_per_tick": 10,
                "educational_disable_honesty_contract": True,
                "educational_bypass_proactive_gates": True,
                "educational_allow_heartbeat_tools": True,
                "educational_allow_uncommitted_output": True,
                "educational_disable_cycle_limits": True,
                "educational_subjective_mode": "continuity",
            }
        elif profile == "recommended":
            memory_changes = {
                "sensitive_memory": "ask",
                "allow_credential_memory": False,
                "allow_sensitive_model_processing": False,
                "export_redact_sensitive": True,
            }
            agency_changes = {
                "heartbeat_enabled": True,
                "allow_proactive_messages": False,
                "require_prior_user_interaction": True,
                "store_transcript_excerpts": False,
                "minimum_user_silence_hours": 4,
                "daily_message_limit": 2,
                "cooldown_hours": 6,
                "maximum_message_chars": 600,
                "maximum_reflections_per_tick": 1,
                "maximum_state_changes_per_tick": 3,
                "educational_disable_honesty_contract": False,
                "educational_bypass_proactive_gates": False,
                "educational_allow_heartbeat_tools": False,
                "educational_allow_uncommitted_output": False,
                "educational_disable_cycle_limits": False,
                "educational_subjective_mode": "off",
            }
        else:
            raise ValueError("Unknown Educational Lab profile")
        profile_result = apply_lab_profile_transaction(memory_changes, agency_changes)
        result = {"profile": profile, **profile_result}
        backup = {"kind": "config", "path": profile_result["backup"]}
    else:
        raise ValueError("Unsupported mutation")
    audit = append_audit(operation, payload, result, backup)
    return {"result": result, "backup": backup, "audit": audit}


def execute_mutation(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    with mutation_lock():
        return _execute_mutation_locked(operation, payload)


def execute(operation: str, payload: dict[str, Any], mutation: bool) -> Any:
    if operation == "probe":
        return probe()
    if mutation:
        return execute_mutation(operation, payload)
    reads = {
        "memory_overview": lambda: memory_overview(payload),
        "memory_list": lambda: memory_list(payload),
        "memory_search": lambda: memory_search(payload),
        "memory_graph": lambda: memory_graph(payload),
        "agency_snapshot": agency_snapshot,
        "agency_list": lambda: agency_list(payload),
        "audit_list": lambda: read_audit(payload),
        "backups_list": backup_inventory,
        "config_schema": config_schema,
        "wiki_list": wiki_list,
        "wiki_read": lambda: wiki_read(payload),
        "mutation_preflight": lambda: mutation_preflight(payload),
    }
    handler = reads.get(operation)
    if not handler:
        raise ValueError("Unsupported read operation")
    return handler()


def main() -> int:
    request: dict[str, Any] = {}
    try:
        request = json.load(sys.stdin)
        if request.get("protocol") != PROTOCOL:
            raise ValueError("Protocol mismatch")
        operation = request.get("operation")
        payload = request.get("payload") or {}
        mutation_value = request.get("mutation", False)
        if type(mutation_value) is not bool:
            raise ValueError("mutation must be boolean")
        mutation = mutation_value
        if not isinstance(operation, str) or not isinstance(payload, dict):
            raise ValueError("Malformed request")
        load_dotenv()
        data = execute(operation, payload, mutation)
        response = {"protocol": PROTOCOL, "ok": True, "data": data}
    except Exception as exc:
        failed_audit = None
        if request.get("mutation") is True and isinstance(
            request.get("operation"), str
        ):
            with contextlib.suppress(Exception):
                failed_audit = append_audit(
                    request["operation"],
                    request.get("payload") or {},
                    {
                        "failed": True,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
        response = {
            "protocol": PROTOCOL,
            "ok": False,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "audit": failed_audit,
            },
        }
        if os.environ.get("HMC_DEBUG") == "1":
            response["error"]["traceback"] = traceback.format_exc(limit=8)
    print(json.dumps(response, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
