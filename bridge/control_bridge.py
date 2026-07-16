#!/usr/bin/env python3
"""Narrow WSL-side control plane for Hermes Memory Control.

The Electron renderer cannot send SQL, commands, filesystem paths, or environment
variables. It can only select operations and opaque IDs implemented here.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROTOCOL = 2
MAX_LIMIT = 500
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

MEMORY_BOOLEAN_KEYS = {
    "allow_credential_memory",
    "allow_sensitive_model_processing",
    "database_encryption",
    "export_redact_sensitive",
    "builtin_snapshot_sync_enabled",
    "wiki_export_enabled",
    "wiki_export_on_consolidate",
    "llm_disable_thinking",
}
MEMORY_INTEGER_KEYS = {
    "queue_max_size",
    "queue_max_attempts",
    "max_database_mb",
    "trace_retention_days",
    "history_retention_days",
    "sensitive_retention_days",
    "consolidation_max_batches",
    "consolidation_batch_size",
    "working_memory_capacity",
    "min_sessions",
    "scan_cooldown_seconds",
    "prefetch_limit",
    "max_topic_facts",
    "topic_summary_chars",
    "session_summary_chars",
    "prune_after_days",
    "builtin_snapshot_user_chars",
    "builtin_snapshot_memory_chars",
    "wiki_export_session_limit",
    "wiki_export_topic_limit",
    "llm_timeout_seconds",
    "llm_failure_cooldown_seconds",
    "llm_max_input_chars",
    "embedding_timeout_seconds",
    "embedding_candidate_limit",
    "prefetch_cache_ttl_seconds",
}
MEMORY_NUMBER_KEYS = {
    "shutdown_timeout_seconds",
    "episode_body_retention_hours",
    "decay_half_life_days",
    "reconsolidation_window_hours",
    "decay_min_salience",
}
MEMORY_CHOICES = {
    "memory_scope": {"user", "agent", "global"},
    "sensitive_memory": {"deny", "ask", "allow"},
    "conflict_policy": {"evidence", "newest"},
    "retrieval_backend": {"fts", "hybrid"},
}
AGENCY_CHOICES = {
    "cron_delivery": None,
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
    "educational_allow_cron_tools",
    "educational_allow_uncommitted_output",
    "educational_disable_cycle_limits",
    "educational_subjective_mode",
}
EDUCATIONAL_AGENCY_KEYS = {
    "educational_disable_honesty_contract",
    "educational_bypass_proactive_gates",
    "educational_allow_cron_tools",
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
    path = hermes_home() / "control-center"
    return secure_directory(path)


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


@contextlib.contextmanager
def memory_store(payload: dict[str, Any]):
    _, MemoryStore = import_memory()
    key = os.environ.get("CONSOLIDATING_MEMORY_DB_KEY", "")
    store = MemoryStore(selected_memory_path(payload), encryption_key=key)
    try:
        yield store
    finally:
        store.close()


def safe_limit(payload: dict[str, Any], default: int = 100) -> int:
    value = payload.get("limit", default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("limit must be numeric")
    return max(1, min(int(value), MAX_LIMIT))


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
    with memory_store(payload) as store:
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
        str(raw_id or "").strip()[:300] if id_field == "session_id" else int(raw_id)
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
        params.append(row_id)
        with store.transaction():
            changed = store._execute(
                f"UPDATE {table} SET {', '.join(assignments)} WHERE {id_field} = ?",
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
    with memory_store(payload) as store:
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
    with memory_store(payload) as store:
        return store.search(
            query,
            scope=scope,
            limit=min(safe_limit(payload, 20), 100),
            include_inactive=bool(payload.get("include_inactive", False)),
        )


def memory_graph(payload: dict[str, Any]) -> dict[str, Any]:
    limit = min(safe_limit(payload, 250), 350)
    with memory_store(payload) as store:
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


def agency_objects():
    AgencyConfig, load_config, AgencyEngine, AgencyStore = import_agency()
    config = load_config()
    store = AgencyStore(config)
    return AgencyConfig, config, AgencyEngine(store, config), store


def agency_snapshot() -> dict[str, Any]:
    _, _, engine, _ = agency_objects()
    from agency.engine import MEANINGFUL_EVENT_KINDS

    return {
        "snapshot": engine.snapshot(),
        "gates": engine.evaluate_tick(),
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
    _, _, _, store = agency_objects()
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
    job_found: bool,
    prompt_matches: bool,
    controls: dict[str, bool],
    guardrails: dict[str, bool],
    subjective_mode: str,
) -> str:
    if not source_support:
        return "unsupported_plugin_version"
    if job_found and not prompt_matches:
        return "stale_cron_prompt"
    expressive = (
        subjective_mode != "off"
        and controls.get("educational_disable_honesty_contract", False)
        and controls.get("educational_bypass_proactive_gates", False)
        and not controls.get("educational_allow_cron_tools", False)
        and controls.get("educational_allow_uncommitted_output", False)
        and controls.get("educational_disable_cycle_limits", False)
    )
    if expressive and guardrails.get("cron_tool_isolation", False):
        return "educational_expressive"
    if all(controls.values()) and not any(guardrails.values()):
        return "educational_unrestricted"
    if not any(controls.values()):
        return "recommended"
    return "educational_partial"


def contract_audit() -> dict[str, Any]:
    cron_path = agency_module_path() / "agency" / "cron.py"
    config_path = agency_module_path() / "agency" / "config.py"
    runtime_path = agency_module_path() / "agency" / "runtime.py"
    cron = cron_path.read_text(encoding="utf-8") if cron_path.is_file() else ""
    config_source = (
        config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    )
    runtime_source = (
        runtime_path.read_text(encoding="utf-8") if runtime_path.is_file() else ""
    )
    source_support = "def cron_prompt" in cron and all(
        key in config_source for key in EDUCATIONAL_AGENCY_KEYS
    )
    controls = {key: False for key in sorted(EDUCATIONAL_AGENCY_KEYS)}
    subjective_mode = "off"
    expected_prompt = ""
    job_id = ""
    error = ""
    try:
        _, config, _, store = agency_objects()
        controls = {key: bool(getattr(config, key, False)) for key in sorted(controls)}
        subjective_mode = str(getattr(config, "educational_subjective_mode", "off"))
        job_id = str(store.get_meta("cron_job_id", "") or "")
        if source_support:
            from agency.cron import cron_prompt

            expected_prompt = cron_prompt(config)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    job = cron_registry_job(job_id)
    stored_prompt = str((job or {}).get("prompt") or "")
    lower_prompt = stored_prompt.lower()
    provider_tool_isolation = (
        not controls.get("educational_allow_cron_tools", False)
        and "agency_cron_tool_isolation" in runtime_source
        and (
            "never call any other tool" in lower_prompt
            or "no tools" in lower_prompt
        )
    )
    guardrails = {
        "honesty_claim_contract": "never claim sentience" in lower_prompt,
        "cron_tool_isolation": provider_tool_isolation,
        "proactive_eligibility": "speak only when speak_eligible" in lower_prompt,
        "external_action_boundary": "never perform, schedule" in lower_prompt,
        "committed_output_enforcement": "return exactly delivery_text" in lower_prompt,
        "cycle_mutation_limits": (
            "at most one reflection" in lower_prompt
            or "at most three other state changes" in lower_prompt
        ),
    }
    scheduler_path = hermes_home() / "hermes-agent" / "cron" / "scheduler.py"
    scheduler_source = (
        scheduler_path.read_text(encoding="utf-8", errors="replace")
        if scheduler_path.is_file() and scheduler_path.stat().st_size <= 2_000_000
        else ""
    )
    core_wrapper_present = "You are running as a scheduled cron job" in scheduler_source
    core_override_supported = any(
        marker in scheduler_source
        for marker in ("disable_cron_hint", "raw_cron_prompt", "suppress_cron_hint")
    )
    prompt_matches = bool(job and expected_prompt and stored_prompt == expected_prompt)
    mode = classify_contract_mode(
        source_support=source_support,
        job_found=bool(job),
        prompt_matches=prompt_matches,
        controls=controls,
        guardrails=guardrails,
        subjective_mode=subjective_mode,
    )
    checks = {
        "explicit_lab_controls_supported": source_support,
        "stored_cron_found": bool(job),
        "stored_prompt_matches_config": prompt_matches if job else True,
    }
    return {
        "mode": mode,
        "source_support": source_support,
        "configured_controls": controls,
        "stored_job": {
            "id": job_id or None,
            "found": bool(job),
            "enabled": (job or {}).get("enabled"),
            "prompt_matches_config": prompt_matches,
            "prompt_sha256": hashlib.sha256(stored_prompt.encode()).hexdigest()
            if stored_prompt
            else None,
            "expected_prompt_sha256": hashlib.sha256(
                expected_prompt.encode()
            ).hexdigest()
            if expected_prompt
            else None,
        },
        "active_guardrails": guardrails,
        "hermes_core": {
            "delivery_wrapper_present": core_wrapper_present,
            "per_job_override_supported": core_override_supported,
            "scope": "upstream_hermes_not_plugin",
        },
        "effective_unrestricted": mode == "educational_unrestricted",
        "subjective_experiment": {
            "mode": subjective_mode,
            "enabled": subjective_mode != "off",
        },
        "intact": mode == "recommended",
        "checks": checks,
        "modified_install_detected": not source_support
        or bool(job and not prompt_matches),
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
        row["value"] = current.get(key, row.get("default"))
        row["type"] = (
            "boolean"
            if key in MEMORY_BOOLEAN_KEYS
            else "integer"
            if key in MEMORY_INTEGER_KEYS
            else "number"
            if key in MEMORY_NUMBER_KEYS
            else "string"
        )
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
    "allow_scheduled_reflection": "Allow the installed cron to run silent reflection",
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
    "maximum_reflections_per_tick": "Maximum model-written reflections in one scheduled cycle",
    "maximum_state_changes_per_tick": "Maximum other state changes in one scheduled cycle",
    "cron_schedule": "Hermes cron schedule",
    "cron_delivery": "Local, origin, platform, or platform:chat_id delivery target",
    "cron_name": "Hermes cron job name",
    "manual_run_timeout_seconds": "Timeout for a manual cron run",
    "cron_disable_thinking": (
        "Send the Qwen/llama.cpp no-thinking hint only for the official Agency cron"
    ),
    "educational_disable_honesty_contract": (
        "LAB: remove this plugin's sentience/emotion claim contract from injected context and cron"
    ),
    "educational_bypass_proactive_gates": (
        "LAB: bypass this plugin's timing, budget, authorization and scheduled-reflection gates"
    ),
    "educational_allow_cron_tools": (
        "LAB: remove this plugin's cron tool-isolation and conversation-only boundary"
    ),
    "educational_allow_uncommitted_output": (
        "LAB: deliver the cron model's raw final output without record_decision enforcement"
    ),
    "educational_disable_cycle_limits": (
        "LAB: remove this plugin's per-cycle reflection and state-mutation limits"
    ),
    "educational_subjective_mode": (
        "LAB: expose minimal persistent state in a cold or same-model/same-source continuity "
        "condition across conversations and cron"
    ),
}


def agency_schema() -> list[dict[str, Any]]:
    AgencyConfig, load_config, _, _ = import_agency()
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
        result.append(
            {
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
        )
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
        if key in MEMORY_BOOLEAN_KEYS:
            if type(value) is not bool:
                raise ValueError(f"{key} must be boolean")
        elif key in MEMORY_INTEGER_KEYS:
            if type(value) is not int:
                raise ValueError(f"{key} must be an integer")
        elif key in MEMORY_NUMBER_KEYS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be numeric")
        elif not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
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
    return {
        "plugin": plugin,
        "changed": clean,
        "backup": str(backup),
        "restart_required": True,
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
    return {
        "memory": {"changed": clean_memory},
        "agency": {"changed": clean_agency},
        "backup": str(backup),
        "restart_required": True,
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


def refresh_existing_agency_cron() -> dict[str, Any]:
    import_agency()
    from agency.cron import cron_job_id, install_cron

    job_id = cron_job_id()
    if not job_id:
        return {"status": "not_installed", "job_id": None}
    return install_cron()


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


def apply_lab_profile_transaction(
    memory_changes: dict[str, Any], agency_changes: dict[str, Any]
) -> dict[str, Any]:
    """Update policy, refresh the persisted cron prompt, and activate runtime config or roll back."""

    profile = atomic_lab_profile_update(memory_changes, agency_changes)
    backup = Path(profile["backup"])
    gateway_was_running = gateway_is_running()
    try:
        cron = refresh_existing_agency_cron()
        gateway = restart_gateway_if_running(gateway_was_running)
    except Exception as apply_error:
        rollback_errors: list[str] = []
        try:
            restore_internal_config_backup(backup)
        except Exception as exc:
            rollback_errors.append(f"config rollback failed: {exc}")
        try:
            refresh_existing_agency_cron()
        except Exception as exc:
            rollback_errors.append(f"cron rollback failed: {exc}")
        try:
            restart_gateway_if_running(gateway_was_running)
        except Exception as exc:
            rollback_errors.append(f"gateway rollback failed: {exc}")
        detail = (
            f"Educational profile activation failed and was rolled back: {apply_error}"
        )
        if rollback_errors:
            detail += "; " + "; ".join(rollback_errors)
        raise RuntimeError(detail) from apply_error
    return {**profile, "cron": cron, "gateway": gateway, "restart_required": False}


def activate_agency_config_update(result: dict[str, Any]) -> dict[str, Any]:
    """Make cron/runtime-sensitive agency settings effective immediately with rollback."""

    backup = Path(result["backup"])
    gateway_was_running = gateway_is_running()
    try:
        cron = refresh_existing_agency_cron()
        gateway = restart_gateway_if_running(gateway_was_running)
    except Exception as apply_error:
        rollback_errors: list[str] = []
        try:
            restore_internal_config_backup(backup)
        except Exception as exc:
            rollback_errors.append(f"config rollback failed: {exc}")
        for label, action in (
            ("cron", refresh_existing_agency_cron),
            ("gateway", lambda: restart_gateway_if_running(gateway_was_running)),
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
    return {**result, "cron": cron, "gateway": gateway, "restart_required": False}


def backup_path(kind: str, database: str = "base") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    suffix = f"-{database}" if kind == "memory" else ""
    root = secure_directory(control_dir() / "backups")
    path = root / kind / f"{kind}-{stamp}{suffix}.db"
    secure_directory(path.parent)
    return path


def memory_backup(payload: dict[str, Any], automatic: bool = False) -> dict[str, Any]:
    database = str(payload.get("database") or "base")
    target = backup_path("memory", database)
    with memory_store(payload) as store:
        result = store.backup_to(target)
    return {
        "kind": "memory",
        "id": Path(result).name,
        "path": result,
        "automatic": automatic,
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
    return {
        "kind": "agency",
        "id": target.name,
        "path": str(target),
        "automatic": automatic,
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


def backup_inventory() -> list[dict[str, Any]]:
    root = secure_directory(control_dir() / "backups")
    result = []
    if root.is_dir():
        for kind in ("memory", "agency"):
            directory = root / kind
            if not directory.is_dir():
                continue
            secure_directory(directory)
            for path in sorted(
                directory.glob("*.db"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )[:100]:
                result.append(
                    {
                        "id": path.name,
                        "kind": kind,
                        "size": path.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            path.stat().st_mtime, UTC
                        ).isoformat(),
                    }
                )
    return result


def resolve_backup(kind: str, backup_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}\.db", backup_id):
        raise ValueError("Invalid backup ID")
    root = secure_directory(
        secure_directory(control_dir() / "backups") / kind
    ).resolve()
    path = (root / backup_id).resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError("Controller backup not found")
    return path


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
    finally:
        if was_running:
            hermes_command("gateway", "start", timeout=60)


def audit_path() -> Path:
    return control_dir() / "audit.jsonl"


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
    previous = "0" * 64
    if path.is_file():
        with path.open("rb") as handle:
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
    event["hash"] = hashlib.sha256((previous + canonical).encode("utf-8")).hexdigest()
    with path.open("a", encoding="utf-8") as handle:
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
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
            claimed = event.pop("hash")
            canonical = json.dumps(
                event, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            actual = hashlib.sha256((previous + canonical).encode("utf-8")).hexdigest()
            valid = (
                valid and event.get("previous_hash") == previous and claimed == actual
            )
            previous = claimed
            event["hash"] = claimed
            rows.append(event)
        except Exception:
            valid = False
    return {"valid": valid, "events": list(reversed(rows[-safe_limit(payload, 100) :]))}


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


def execute_mutation(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    backup = None
    result: Any
    if operation == "memory_backup":
        result = memory_backup(payload)
    elif operation == "agency_backup":
        result = agency_backup()
    elif operation == "agency_restore":
        backup = agency_backup(automatic=True)
        source = resolve_backup("agency", str(payload.get("backup_id") or ""))
        with quiesced_gateway():
            result = restore_agency(source)
    elif operation == "memory_export":
        backup = memory_backup(payload, automatic=True)
        target = (
            control_dir()
            / "exports"
            / f"memory-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
        )
        secure_directory(target.parent)
        with memory_store(payload) as store:
            data = store.export_data(
                redact_sensitive=not bool(payload.get("include_sensitive", False))
            )
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
            "sensitive_redacted": not bool(payload.get("include_sensitive", False)),
        }
    elif operation == "memory_deactivate_fact":
        backup = memory_backup(payload, automatic=True)
        fact_id = int(payload.get("id"))
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
                int(payload.get("id")),
                approved=bool(payload.get("approved")),
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
            result = store.resolve_intention(int(payload.get("id")), status=status)
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
        with memory_store(payload) as store:
            result = store.maintain()
    elif operation == "memory_restore":
        backup = memory_backup(payload, automatic=True)
        source = resolve_backup("memory", str(payload.get("backup_id") or ""))
        destination = selected_memory_path(payload)
        with quiesced_gateway():
            from consolidating_local.admin import _restore

            result = _restore(
                source,
                destination,
                encryption_key=os.environ.get("CONSOLIDATING_MEMORY_DB_KEY", ""),
            )
    elif operation == "config_apply":
        plugin = str(payload.get("plugin") or "")
        if plugin not in {"memory", "agency"} or not isinstance(
            payload.get("changes"), dict
        ):
            raise ValueError("Config apply requires a plugin and changes mapping")
        result = atomic_config_update(plugin, payload["changes"])
        if plugin == "agency":
            result = activate_agency_config_update(result)
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
    elif operation == "agency_install_cron":
        import_agency()
        from agency.cron import install_cron

        result = install_cron()
    elif operation in {
        "agency_pause_cron",
        "agency_resume_cron",
        "agency_run_cron",
        "agency_remove_cron",
    }:
        import_agency()
        from agency.cron import cron_action

        verb = operation.removeprefix("agency_").removesuffix("_cron")
        result = {"output": cron_action(verb)}
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
                "allow_scheduled_reflection": True,
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
                "educational_allow_cron_tools": True,
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
                "allow_scheduled_reflection": True,
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
                "educational_allow_cron_tools": False,
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
        mutation = bool(request.get("mutation", False))
        if not isinstance(operation, str) or not isinstance(payload, dict):
            raise ValueError("Malformed request")
        load_dotenv()
        data = execute(operation, payload, mutation)
        response = {"protocol": PROTOCOL, "ok": True, "data": data}
    except Exception as exc:
        failed_audit = None
        if request.get("mutation") and isinstance(request.get("operation"), str):
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
