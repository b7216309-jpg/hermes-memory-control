from __future__ import annotations

import importlib.util
import contextlib
import concurrent.futures
import json
import os
import sqlite3
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "control_bridge", ROOT / "bridge" / "control_bridge.py"
)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(bridge)


class BridgeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.get("HERMES_HOME")
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / ".hermes"
        self.home.mkdir()
        os.environ["HERMES_HOME"] = str(self.home)

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.previous
        self.temp.cleanup()

    def test_audit_chain_verifies_and_detects_tampering(self):
        first = bridge.append_audit("test_one", {"value": 1}, {"ok": True})
        second = bridge.append_audit("test_two", {"value": 2}, {"ok": True})
        self.assertNotEqual(first["hash"], second["hash"])
        self.assertTrue(bridge.read_audit({"limit": 20})["valid"])
        path = bridge.audit_path()
        lines = path.read_text(encoding="utf-8").splitlines()
        item = json.loads(lines[0])
        item["operation"] = "tampered"
        lines[0] = json.dumps(item)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertFalse(bridge.read_audit({"limit": 20})["valid"])

    def test_concurrent_audit_appends_keep_one_valid_chain(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda index: bridge.append_audit(
                        "concurrent_test", {"index": index}, {"ok": True}
                    ),
                    range(24),
                )
            )
        self.assertEqual(len({item["hash"] for item in results}), 24)
        report = bridge.read_audit({"limit": 100})
        self.assertTrue(report["valid"])
        self.assertEqual(len(report["events"]), 24)

    def test_dotenv_loads_valid_names_without_overwriting_environment(self):
        (self.home / ".env").write_text(
            "GOOD_VALUE='hello world'\nINVALID-NAME=no\nEXISTING=from-file\n",
            encoding="utf-8",
        )
        os.environ["EXISTING"] = "from-process"
        try:
            bridge.load_dotenv()
            self.assertEqual(os.environ["GOOD_VALUE"], "hello world")
            self.assertNotIn("INVALID-NAME", os.environ)
            self.assertEqual(os.environ["EXISTING"], "from-process")
        finally:
            os.environ.pop("GOOD_VALUE", None)
            os.environ.pop("EXISTING", None)

    def test_legacy_memory_store_allows_backup_but_refuses_unsafe_reads(self):
        class LegacyStore:
            def __init__(self, path, encryption_key=""):
                self.path = path
                self.encryption_key = encryption_key

            def close(self):
                pass

        target = self.home / "memory.db"
        with (
            mock.patch.object(bridge, "import_memory", return_value=(None, LegacyStore)),
            mock.patch.object(bridge, "selected_memory_path", return_value=target),
        ):
            with bridge.memory_store({}, read_only=False) as store:
                self.assertEqual(store.path, target)
            with self.assertRaisesRegex(RuntimeError, "too old for safe read-only"):
                with bridge.memory_store({}, read_only=True):
                    pass

    def test_legacy_agency_store_allows_backup_path_but_refuses_unsafe_reads(self):
        class LegacyStore:
            def __init__(self, config):
                self.config = config

        config = SimpleNamespace()
        imported = (
            object,
            lambda: config,
            lambda store, current: SimpleNamespace(store=store, config=current),
            LegacyStore,
        )
        with mock.patch.object(bridge, "import_agency", return_value=imported):
            _, _, engine, store = bridge.agency_objects(read_only=False)
            self.assertIs(engine.store, store)
            with self.assertRaisesRegex(RuntimeError, "too old for safe read-only"):
                bridge.agency_objects(read_only=True)

    def test_current_store_contract_receives_read_only_mode(self):
        class CurrentStore:
            def __init__(self, path, encryption_key="", read_only=False):
                self.read_only = read_only

            def close(self):
                pass

        with (
            mock.patch.object(bridge, "import_memory", return_value=(None, CurrentStore)),
            mock.patch.object(
                bridge, "selected_memory_path", return_value=self.home / "memory.db"
            ),
        ):
            with bridge.memory_store({}, read_only=True) as store:
                self.assertTrue(store.read_only)

    def test_backup_ids_cannot_escape_controller_directory(self):
        with self.assertRaises(ValueError):
            bridge.resolve_backup("memory", "../secret.db")
        with self.assertRaises(ValueError):
            bridge.resolve_backup("agency", "not-a-database.txt")
        with self.assertRaises(ValueError):
            bridge.backup_path("memory", "../../escape")
        self.assertFalse((self.home / "control-center").exists())

    def test_backup_manifest_binds_digest_target_and_encryption(self):
        path = (
            self.home / "control-center" / "backups" / "memory" / "memory-test-base.db"
        )
        path.parent.mkdir(parents=True)
        path.write_bytes(b"synthetic encrypted database bytes")
        bridge.write_backup_manifest(
            path,
            kind="memory",
            database="base",
            plugin_version="test",
            encrypted=True,
            schema={"user_version": 1, "table_count": 2, "tables_sha256": "a" * 64},
        )
        verified = bridge.verify_backup_manifest(
            path, kind="memory", database="base", encrypted=True
        )
        self.assertTrue(verified["verified"])
        with self.assertRaisesRegex(RuntimeError, "encryption mode"):
            bridge.verify_backup_manifest(
                path, kind="memory", database="base", encrypted=False
            )
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "digest"):
            bridge.verify_backup_manifest(
                path, kind="memory", database="base", encrypted=True
            )

    def test_retention_prunes_only_manifested_automatic_backups(self):
        root = self.home / "control-center" / "backups" / "memory"
        root.mkdir(parents=True)
        for index in range(4):
            path = root / f"memory-test-{index}-base.db"
            path.write_bytes(f"backup-{index}".encode())
            bridge.write_backup_manifest(
                path,
                kind="memory",
                database="base",
                plugin_version="test",
                encrypted=True,
                schema={
                    "user_version": 1,
                    "table_count": 2,
                    "tables_sha256": "a" * 64,
                },
                automatic=index < 3,
            )
            os.utime(path, (index + 1, index + 1))
        legacy = root / "memory-legacy-base.db"
        legacy.write_bytes(b"legacy")

        with mock.patch.object(bridge, "AUTOMATIC_BACKUPS_PER_TARGET", 2):
            self.assertEqual(
                bridge.prune_automatic_backups(kind="memory", database="base"), 1
            )
        remaining = {path.name for path in root.glob("*.db")}
        self.assertIn("memory-test-3-base.db", remaining)  # manual
        self.assertIn(legacy.name, remaining)
        self.assertEqual(len(remaining), 4)

    def test_config_backup_retention_does_not_touch_unrelated_files(self):
        root = self.home / "control-center" / "config-backups"
        root.mkdir(parents=True)
        backups = []
        for index in range(4):
            path = root / f"config-{index}.yaml"
            path.write_text(str(index), encoding="utf-8")
            os.utime(path, (index + 1, index + 1))
            backups.append(path)
        unrelated = root / "operator-notes.yaml"
        unrelated.write_text("keep", encoding="utf-8")

        with mock.patch.object(bridge, "CONFIG_BACKUP_RETENTION", 2):
            self.assertEqual(bridge.prune_config_backups(preserve=backups[-1]), 2)
        self.assertTrue(backups[-1].is_file())
        self.assertTrue(unrelated.is_file())

    def test_reading_empty_control_state_does_not_create_directories(self):
        root = self.home / "control-center"
        self.assertFalse(root.exists())
        self.assertEqual(bridge.read_audit({"limit": 10})["events"], [])
        self.assertEqual(bridge.backup_inventory(), [])
        self.assertFalse(root.exists())

    def test_hermes_home_must_end_in_dot_hermes(self):
        os.environ["HERMES_HOME"] = str(Path(self.temp.name) / "wrong")
        with self.assertRaises(RuntimeError):
            bridge.hermes_home()

    def test_config_redaction_never_returns_secret_values(self):
        value = bridge.redact_config(
            {"api_key": "secret", "database_key_env": "KEY", "safe": 4}
        )
        self.assertEqual(value["api_key"], "<redacted>")
        self.assertEqual(value["database_key_env"], "<redacted>")
        self.assertEqual(value["safe"], 4)

    def test_subjective_journal_is_read_only_and_lab_scoped(self):
        self.assertEqual(bridge.AGENCY_TABLES["subjective"], "subjective_entries")
        self.assertIn("educational_subjective_mode", bridge.LAB_AGENCY_KEYS)
        self.assertEqual(
            bridge.AGENCY_CHOICES["educational_subjective_mode"],
            {"off", "cold", "continuity"},
        )

    def test_expressive_contract_shape_is_distinct_from_unrestricted(self):
        controls = {key: True for key in bridge.EDUCATIONAL_AGENCY_KEYS}
        controls["educational_allow_heartbeat_tools"] = False
        mode = bridge.classify_contract_mode(
            source_support=True,
            legacy_cron_found=False,
            controls=controls,
            guardrails={"heartbeat_tool_isolation": True},
            subjective_mode="continuity",
        )

        self.assertEqual(mode, "educational_expressive")

    def test_audit_safely_hashes_memory_text_and_nested_secrets(self):
        safe = bridge.audit_safe(
            {
                "table": "facts",
                "changes": {"content": "private memory", "api_key": "secret"},
            }
        )
        self.assertEqual(safe["table"], "facts")
        self.assertEqual(safe["changes"]["content"]["chars"], len("private memory"))
        self.assertEqual(len(safe["changes"]["content"]["text_sha256"]), 64)
        self.assertEqual(safe["changes"]["api_key"], "<redacted>")

    def test_memory_patch_is_allowlisted_typed_and_noop_aware(self):
        current = {
            "content": "old",
            "importance": 5,
            "active": 1,
            "fingerprint": "immutable",
        }
        clean = bridge.validate_memory_patch(
            "facts", {"content": "new", "importance": 8, "active": False}, current
        )
        self.assertEqual(clean, {"content": "new", "importance": 8, "active": 0})
        with self.assertRaises(ValueError):
            bridge.validate_memory_patch("facts", {"fingerprint": "forged"}, current)
        with self.assertRaises(ValueError):
            bridge.validate_memory_patch("facts", {"importance": 99}, current)
        with self.assertRaises(ValueError):
            bridge.validate_memory_patch("facts", {"content": "old"}, current)

    def test_temporal_fact_patch_enforces_cross_field_invariants(self):
        current = {
            "temporal_kind": "atemporal",
            "event_at": 0.0,
            "valid_from": 0.0,
            "valid_until": 0.0,
            "temporal_precision": "unknown",
            "temporal_timezone": "",
            "temporal_confidence": 0.0,
        }
        clean = bridge.validate_memory_patch(
            "facts",
            {
                "temporal_kind": "scheduled",
                "event_at": 1784185200.0,
                "valid_until": 1784271600.0,
                "temporal_precision": "minute",
                "temporal_timezone": "Europe/Paris",
                "temporal_confidence": 0.95,
            },
            current,
        )
        self.assertEqual(clean["temporal_kind"], "scheduled")
        with self.assertRaisesRegex(ValueError, "require event_at"):
            bridge.validate_memory_patch("facts", {"temporal_kind": "event"}, current)
        with self.assertRaisesRegex(ValueError, "later than event_at"):
            bridge.validate_memory_patch(
                "facts",
                {"temporal_kind": "scheduled", "event_at": 20.0, "valid_until": 10.0},
                current,
            )
        with self.assertRaisesRegex(ValueError, "valid IANA timezone"):
            bridge.validate_memory_patch(
                "facts", {"temporal_timezone": "Mars/Olympus"}, current
            )
        with self.assertRaisesRegex(ValueError, "non-negative number"):
            bridge.validate_memory_patch("facts", {"event_at": float("nan")}, current)

    def test_temporal_memory_update_syncs_metadata_and_timeline(self):
        class FakeStore:
            def __init__(self):
                self.connection = sqlite3.connect(":memory:")
                self.connection.row_factory = sqlite3.Row
                self.connection.execute(
                    """CREATE TABLE facts(
                        id INTEGER PRIMARY KEY, content TEXT, importance INTEGER,
                        sensitivity TEXT, temporal_kind TEXT, event_at REAL,
                        valid_from REAL, valid_until REAL, temporal_precision TEXT,
                        temporal_timezone TEXT, temporal_confidence REAL,
                        metadata_json TEXT, updated_at REAL, revision INTEGER
                    )"""
                )
                self.connection.execute(
                    "INSERT INTO facts VALUES (1, 'Synthetic inspection', 7, 'normal', "
                    "'atemporal', 0, 0, 0, 'unknown', '', 0, '{}', 1, 1)"
                )
                self.connection.commit()
                self.events = []
                self.links = []
                self.history = []
                self.refreshed = []
                self.topic_rebuilds = 0

            def _fetchone(self, sql, params=()):
                row = self.connection.execute(sql, tuple(params)).fetchone()
                if not row:
                    return None
                item = dict(row)
                if "metadata_json" in item:
                    item["metadata"] = json.loads(item.get("metadata_json") or "{}")
                return item

            def _execute(self, sql, params=()):
                return self.connection.execute(sql, tuple(params))

            @contextlib.contextmanager
            def transaction(self):
                self.connection.execute("BEGIN")
                try:
                    yield
                except Exception:
                    self.connection.rollback()
                    raise
                else:
                    self.connection.commit()

            def upsert_autobiographical_event(self, **values):
                event = {"id": 91, **values}
                self.events.append(event)
                return event

            def add_link(self, *values):
                self.links.append(values)

            def record_history(self, **values):
                self.history.append(values)
                return values

            def refresh_search_document(self, logical, row):
                self.refreshed.append((logical, dict(row)))

            def rebuild_topics(self):
                self.topic_rebuilds += 1
                return 1

        store = FakeStore()
        columns = [
            "id",
            "content",
            "importance",
            "sensitivity",
            "temporal_kind",
            "event_at",
            "valid_from",
            "valid_until",
            "temporal_precision",
            "temporal_timezone",
            "temporal_confidence",
            "metadata_json",
            "updated_at",
            "revision",
        ]
        with (
            mock.patch.object(
                bridge, "memory_store", return_value=contextlib.nullcontext(store)
            ),
            mock.patch.object(bridge, "table_columns_memory", return_value=columns),
        ):
            result = bridge.memory_update_item(
                {
                    "database": "base",
                    "table": "facts",
                    "id": 1,
                    "changes": {
                        "temporal_kind": "scheduled",
                        "event_at": 1784185200.0,
                        "valid_until": 1784271600.0,
                        "temporal_precision": "minute",
                        "temporal_timezone": "Europe/Paris",
                        "temporal_confidence": 0.95,
                    },
                }
            )

        self.assertEqual(result["item"]["metadata"]["temporal_kind"], "scheduled")
        self.assertEqual(store.events[0]["event_key"], "fact-1")
        self.assertEqual(
            store.events[0]["metadata"]["temporal_timezone"], "Europe/Paris"
        )
        self.assertEqual(
            store.links[0], ("fact", 1, "autobiographical_event", 91, "represented_by")
        )
        self.assertEqual(store.refreshed[0][0], "facts")
        self.assertEqual(store.topic_rebuilds, 1)
        self.assertEqual(store.history[0]["action"], "operator_updated")

    def test_memory_update_is_transactional_and_records_plugin_history(self):
        class FakeStore:
            def __init__(self):
                self.connection = sqlite3.connect(":memory:")
                self.connection.row_factory = sqlite3.Row
                self.connection.execute(
                    "CREATE TABLE topics(id INTEGER PRIMARY KEY, title TEXT, summary TEXT, category TEXT, importance INTEGER, salience REAL, sensitivity TEXT, updated_at REAL)"
                )
                self.connection.execute(
                    "INSERT INTO topics VALUES (1, 'old', '', 'general', 5, .5, 'normal', 1)"
                )
                self.connection.commit()
                self.history = []
                self.refreshed = []

            def _fetchone(self, sql, params=()):
                row = self.connection.execute(sql, tuple(params)).fetchone()
                return dict(row) if row else None

            def _execute(self, sql, params=()):
                return self.connection.execute(sql, tuple(params))

            @contextlib.contextmanager
            def transaction(self):
                self.connection.execute("BEGIN")
                try:
                    yield
                except Exception:
                    self.connection.rollback()
                    raise
                else:
                    self.connection.commit()

            def record_history(self, **values):
                self.history.append(values)
                return values

            def refresh_search_document(self, logical, row):
                self.refreshed.append((logical, dict(row)))

        store = FakeStore()
        with (
            mock.patch.object(
                bridge, "memory_store", return_value=contextlib.nullcontext(store)
            ),
            mock.patch.object(
                bridge,
                "table_columns_memory",
                return_value=[
                    "id",
                    "title",
                    "summary",
                    "category",
                    "importance",
                    "salience",
                    "sensitivity",
                    "updated_at",
                ],
            ),
        ):
            result = bridge.memory_update_item(
                {
                    "database": "base",
                    "table": "topics",
                    "id": 1,
                    "changes": {"title": "new", "importance": 9},
                }
            )
        self.assertEqual(result["item"]["title"], "new")
        self.assertEqual(result["item"]["importance"], 9)
        self.assertEqual(store.refreshed[0][0], "topics")
        self.assertEqual(store.history[0]["action"], "operator_updated")

    def test_memory_update_rejects_concurrent_revision_change(self):
        class RacingStore:
            def __init__(self):
                self.connection = sqlite3.connect(":memory:")
                self.connection.row_factory = sqlite3.Row
                self.connection.execute(
                    "CREATE TABLE topics(id INTEGER PRIMARY KEY, title TEXT, summary TEXT, "
                    "category TEXT, importance INTEGER, salience REAL, sensitivity TEXT, "
                    "updated_at REAL, revision INTEGER)"
                )
                self.connection.execute(
                    "INSERT INTO topics VALUES (1, 'old', '', 'general', 5, .5, 'normal', 1, 1)"
                )
                self.connection.commit()

            def _fetchone(self, sql, params=()):
                row = self.connection.execute(sql, tuple(params)).fetchone()
                return dict(row) if row else None

            def _execute(self, sql, params=()):
                return self.connection.execute(sql, tuple(params))

            @contextlib.contextmanager
            def transaction(self):
                self.connection.execute("UPDATE topics SET revision=2 WHERE id=1")
                self.connection.commit()
                self.connection.execute("BEGIN")
                try:
                    yield
                except Exception:
                    self.connection.rollback()
                    raise
                else:
                    self.connection.commit()

        store = RacingStore()
        columns = [
            "id",
            "title",
            "summary",
            "category",
            "importance",
            "salience",
            "sensitivity",
            "updated_at",
            "revision",
        ]
        with (
            mock.patch.object(
                bridge, "memory_store", return_value=contextlib.nullcontext(store)
            ),
            mock.patch.object(bridge, "table_columns_memory", return_value=columns),
        ):
            with self.assertRaisesRegex(RuntimeError, "concurrently"):
                bridge.memory_update_item(
                    {
                        "database": "base",
                        "table": "topics",
                        "id": 1,
                        "changes": {"title": "new"},
                    }
                )
        self.assertEqual(
            store._fetchone("SELECT * FROM topics WHERE id=1")["title"], "old"
        )

    def test_strict_boolean_payloads_reject_truthy_strings_and_numbers(self):
        self.assertTrue(
            bridge.strict_bool({"approved": True}, "approved", required=True)
        )
        self.assertFalse(bridge.strict_bool({}, "include_sensitive"))
        for value in ("true", "false", 1, 0, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "must be boolean"):
                    bridge.strict_bool({"approved": value}, "approved", required=True)

    def test_protocol_rejects_truthy_string_mutation_flag(self):
        request = {
            "protocol": bridge.PROTOCOL,
            "operation": "probe",
            "payload": {},
            "mutation": "false",
        }
        output = StringIO()
        with (
            mock.patch("sys.stdin", StringIO(json.dumps(request))),
            mock.patch("sys.stdout", output),
        ):
            self.assertEqual(bridge.main(), 0)
        response = json.loads(output.getvalue())
        self.assertFalse(response["ok"])
        self.assertIn("mutation must be boolean", response["error"]["message"])
        self.assertFalse((self.home / "control-center").exists())

    def test_mutation_rejects_missing_or_stale_preflight_token(self):
        with self.assertRaisesRegex(ValueError, "preflight token"):
            bridge.execute_mutation("gateway_restart", {})
        with mock.patch.object(
            bridge,
            "mutation_preflight",
            return_value={"token": "b" * 64, "validated_at": bridge.now_iso()},
        ):
            with self.assertRaisesRegex(RuntimeError, "changed after preview"):
                bridge.execute_mutation(
                    "gateway_restart", {"_preflight_token": "a" * 64}
                )

    def test_preflight_token_changes_with_target_database_state(self):
        database = self.home / "memory.db"
        database.write_bytes(b"first")
        (self.home / "config.yaml").write_text(
            "plugins:\n  consolidating-local-memory:\n"
            "    db_path: $HERMES_HOME/memory.db\n",
            encoding="utf-8",
        )
        request = {
            "action": "memory_backup",
            "payload": {"database": "base"},
        }
        first = bridge.mutation_preflight(request)["token"]
        database.write_bytes(b"second")
        second = bridge.mutation_preflight(request)["token"]
        self.assertNotEqual(first, second)

    def test_preflight_rejects_unknown_payload_fields(self):
        with self.assertRaisesRegex(ValueError, "Unsupported payload field"):
            bridge.mutation_preflight(
                {
                    "action": "gateway_restart",
                    "payload": {"hidden": "not part of the operation contract"},
                }
            )

    def test_preflight_token_changes_with_installed_implementation(self):
        memory_source = self.home / "memory-plugin"
        memory_source.mkdir()
        for relative in (
            "__init__.py",
            "admin.py",
            "llm_client.py",
            "origin.py",
            "store.py",
            "plugin.yaml",
        ):
            (memory_source / relative).write_text("first", encoding="utf-8")
        agency_source = self.home / "agency-plugin"
        (agency_source / "agency").mkdir(parents=True)
        for relative in (
            "agency/config.py",
            "agency/engine.py",
            "agency/heartbeat.py",
            "agency/runtime.py",
            "agency/store.py",
            "agency/tools.py",
            "plugin.yaml",
        ):
            path = agency_source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("first", encoding="utf-8")
        request = {"action": "gateway_restart", "payload": {}}
        with (
            mock.patch.object(bridge, "memory_module_path", return_value=memory_source),
            mock.patch.object(bridge, "agency_module_path", return_value=agency_source),
        ):
            first = bridge.mutation_preflight(request)["token"]
            (agency_source / "agency" / "heartbeat.py").write_text(
                "second", encoding="utf-8"
            )
            second = bridge.mutation_preflight(request)["token"]
        self.assertNotEqual(first, second)

    def test_agency_restore_replaces_database_from_verified_backup(self):
        source = self.home / "source.db"
        destination = self.home / "agency.db"
        for path, value in ((source, "backup"), (destination, "current")):
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
            connection.execute("INSERT INTO sample VALUES (?)", (value,))
            connection.commit()
            connection.close()
        config = SimpleNamespace(database_encryption=False, db_path=destination)
        store = SimpleNamespace(_driver=sqlite3)
        with mock.patch.object(
            bridge, "agency_objects", return_value=(None, config, None, store)
        ):
            result = bridge.restore_agency(source)
        connection = sqlite3.connect(destination)
        try:
            self.assertEqual(
                connection.execute("SELECT value FROM sample").fetchone()[0], "backup"
            )
        finally:
            connection.close()
        self.assertEqual(result["restored_from"], str(source))

    def test_quiesced_gateway_preserves_stopped_state(self):
        stopped = SimpleNamespace(returncode=1, stdout="Gateway not running", stderr="")
        with (
            mock.patch.object(bridge.subprocess, "run", return_value=stopped),
            mock.patch.object(bridge, "hermes_command") as command,
        ):
            with bridge.quiesced_gateway() as state:
                self.assertFalse(state["was_running"])
        command.assert_not_called()

    def test_quiesced_gateway_restarts_only_when_it_was_running(self):
        running = SimpleNamespace(returncode=0, stdout="Gateway running", stderr="")
        with (
            mock.patch.object(bridge.subprocess, "run", return_value=running),
            mock.patch.object(bridge, "hermes_command") as command,
        ):
            with bridge.quiesced_gateway() as state:
                self.assertTrue(state["was_running"])
        self.assertEqual(
            command.call_args_list,
            [
                mock.call("gateway", "stop", timeout=45),
                mock.call("gateway", "start", timeout=60),
            ],
        )

    def test_quiesced_gateway_preserves_operation_and_restart_errors(self):
        running = SimpleNamespace(returncode=0, stdout="Gateway running", stderr="")
        with (
            mock.patch.object(bridge.subprocess, "run", return_value=running),
            mock.patch.object(
                bridge,
                "hermes_command",
                side_effect=[{"output": "stopped"}, RuntimeError("start failed")],
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "restore failed; gateway restart also failed: start failed"
            ):
                with bridge.quiesced_gateway():
                    raise RuntimeError("restore failed")

    def test_mutation_lock_rejects_overlapping_controller_mutation(self):
        with bridge.mutation_lock():
            with self.assertRaisesRegex(RuntimeError, "already in progress"):
                with bridge.mutation_lock():
                    self.fail("overlapping mutation unexpectedly acquired the lease")

    def test_cron_registry_audit_selects_only_recorded_job(self):
        directory = self.home / "cron"
        directory.mkdir()
        (directory / "jobs.json").write_text(
            json.dumps(
                {
                    "jobs": [
                        {"id": "other", "prompt": "unrelated"},
                        {"id": "agency-job", "prompt": "expected", "enabled": True},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(bridge.cron_registry_job("agency-job")["prompt"], "expected")
        self.assertIsNone(bridge.cron_registry_job("missing"))

    def test_lab_profile_transaction_restarts_runtime(self):
        backup = self.home / "control-center" / "config-backups" / "config.yaml"
        with (
            mock.patch.object(
                bridge,
                "atomic_lab_profile_update",
                return_value={"backup": str(backup), "restart_required": True},
            ),
            mock.patch.object(
                bridge,
                "restart_gateway_if_running",
                return_value={"status": "restarted"},
            ) as restart,
            mock.patch.object(
                bridge, "validate_plugin_health", return_value={"ok": True}
            ),
            mock.patch.object(bridge, "gateway_is_running", return_value=True),
        ):
            result = bridge.apply_lab_profile_transaction({}, {})
        restart.assert_called_once_with(True)
        self.assertFalse(result["restart_required"])

    def test_lab_profile_transaction_rolls_back_on_gateway_failure(self):
        backup = self.home / "control-center" / "config-backups" / "config.yaml"
        with (
            mock.patch.object(
                bridge,
                "atomic_lab_profile_update",
                return_value={"backup": str(backup), "restart_required": True},
            ),
            mock.patch.object(
                bridge,
                "restart_gateway_if_running",
                side_effect=[RuntimeError("restart failed"), {"status": "restarted"}],
            ) as restart,
            mock.patch.object(bridge, "restore_internal_config_backup") as restore,
            mock.patch.object(
                bridge, "validate_plugin_health", return_value={"ok": True}
            ),
            mock.patch.object(bridge, "gateway_is_running", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                bridge.apply_lab_profile_transaction({}, {})
        restore.assert_called_once_with(backup)
        self.assertEqual(restart.call_args_list, [mock.call(True), mock.call(True)])

    def test_gateway_activation_restores_original_running_state(self):
        with (
            mock.patch.object(bridge, "gateway_is_running", return_value=False),
            mock.patch.object(
                bridge, "hermes_command", return_value={"output": "started"}
            ) as command,
        ):
            result = bridge.restart_gateway_if_running(True)
        command.assert_called_once_with("gateway", "start", timeout=90)
        self.assertEqual(result["status"], "restored_running")

        with mock.patch.object(bridge, "hermes_command") as command:
            self.assertEqual(
                bridge.restart_gateway_if_running(False)["status"], "preserved_stopped"
            )
        command.assert_not_called()

    def test_standalone_heartbeat_wake_bootstraps_installed_agency_import(self):
        package = ModuleType("agency")
        package.__path__ = []
        heartbeat = ModuleType("agency.heartbeat")
        heartbeat.request_heartbeat_wake = lambda intent, reason: "request-1"
        with (
            mock.patch.dict(
                "sys.modules", {"agency": package, "agency.heartbeat": heartbeat}
            ),
            mock.patch.object(bridge, "import_agency") as bootstrap,
            mock.patch.object(
                bridge,
                "mutation_preflight",
                return_value={"token": "a" * 64, "validated_at": bridge.now_iso()},
            ),
        ):
            result = bridge.execute_mutation(
                "agency_heartbeat_run", {"_preflight_token": "a" * 64}
            )
        bootstrap.assert_called_once_with()
        self.assertEqual(result["result"]["request_id"], "request-1")


if __name__ == "__main__":
    unittest.main()
