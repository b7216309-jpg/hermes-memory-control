from __future__ import annotations

import importlib.util
import contextlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("control_bridge", ROOT / "bridge" / "control_bridge.py")
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

    def test_backup_ids_cannot_escape_controller_directory(self):
        with self.assertRaises(ValueError):
            bridge.resolve_backup("memory", "../secret.db")
        with self.assertRaises(ValueError):
            bridge.resolve_backup("agency", "not-a-database.txt")

    def test_hermes_home_must_end_in_dot_hermes(self):
        os.environ["HERMES_HOME"] = str(Path(self.temp.name) / "wrong")
        with self.assertRaises(RuntimeError):
            bridge.hermes_home()

    def test_config_redaction_never_returns_secret_values(self):
        value = bridge.redact_config({"api_key": "secret", "database_key_env": "KEY", "safe": 4})
        self.assertEqual(value["api_key"], "<redacted>")
        self.assertEqual(value["database_key_env"], "<redacted>")
        self.assertEqual(value["safe"], 4)

    def test_audit_safely_hashes_memory_text_and_nested_secrets(self):
        safe = bridge.audit_safe(
            {"table": "facts", "changes": {"content": "private memory", "api_key": "secret"}}
        )
        self.assertEqual(safe["table"], "facts")
        self.assertEqual(safe["changes"]["content"]["chars"], len("private memory"))
        self.assertEqual(len(safe["changes"]["content"]["text_sha256"]), 64)
        self.assertEqual(safe["changes"]["api_key"], "<redacted>")

    def test_memory_patch_is_allowlisted_typed_and_noop_aware(self):
        current = {"content": "old", "importance": 5, "active": 1, "fingerprint": "immutable"}
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

        store = FakeStore()
        with mock.patch.object(bridge, "memory_store", return_value=contextlib.nullcontext(store)), mock.patch.object(
            bridge,
            "table_columns_memory",
            return_value=["id", "title", "summary", "category", "importance", "salience", "sensitivity", "updated_at"],
        ):
            result = bridge.memory_update_item(
                {"database": "base", "table": "topics", "id": 1, "changes": {"title": "new", "importance": 9}}
            )
        self.assertEqual(result["item"]["title"], "new")
        self.assertEqual(result["item"]["importance"], 9)
        self.assertEqual(store.history[0]["action"], "operator_updated")

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
        with mock.patch.object(bridge, "agency_objects", return_value=(None, config, None, store)):
            result = bridge.restore_agency(source)
        connection = sqlite3.connect(destination)
        try:
            self.assertEqual(connection.execute("SELECT value FROM sample").fetchone()[0], "backup")
        finally:
            connection.close()
        self.assertEqual(result["restored_from"], str(source))

    def test_quiesced_gateway_preserves_stopped_state(self):
        stopped = SimpleNamespace(returncode=1, stdout="Gateway not running", stderr="")
        with mock.patch.object(bridge.subprocess, "run", return_value=stopped), mock.patch.object(
            bridge, "hermes_command"
        ) as command:
            with bridge.quiesced_gateway() as state:
                self.assertFalse(state["was_running"])
        command.assert_not_called()

    def test_quiesced_gateway_restarts_only_when_it_was_running(self):
        running = SimpleNamespace(returncode=0, stdout="Gateway running", stderr="")
        with mock.patch.object(bridge.subprocess, "run", return_value=running), mock.patch.object(
            bridge, "hermes_command"
        ) as command:
            with bridge.quiesced_gateway() as state:
                self.assertTrue(state["was_running"])
        self.assertEqual(command.call_args_list, [mock.call("gateway", "stop", timeout=45), mock.call("gateway", "start", timeout=60)])

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

    def test_lab_profile_transaction_refreshes_cron_and_runtime(self):
        backup = self.home / "control-center" / "config-backups" / "config.yaml"
        with mock.patch.object(
            bridge,
            "atomic_lab_profile_update",
            return_value={"backup": str(backup), "restart_required": True},
        ), mock.patch.object(
            bridge, "refresh_existing_agency_cron", return_value={"status": "updated"}
        ) as refresh, mock.patch.object(
            bridge, "restart_gateway_if_running", return_value={"status": "restarted"}
        ) as restart, mock.patch.object(bridge, "gateway_is_running", return_value=True):
            result = bridge.apply_lab_profile_transaction({}, {})
        refresh.assert_called_once_with()
        restart.assert_called_once_with(True)
        self.assertFalse(result["restart_required"])
        self.assertEqual(result["cron"]["status"], "updated")

    def test_lab_profile_transaction_rolls_back_on_cron_refresh_failure(self):
        backup = self.home / "control-center" / "config-backups" / "config.yaml"
        with mock.patch.object(
            bridge,
            "atomic_lab_profile_update",
            return_value={"backup": str(backup), "restart_required": True},
        ), mock.patch.object(
            bridge,
            "refresh_existing_agency_cron",
            side_effect=[RuntimeError("refresh failed"), {"status": "updated"}],
        ), mock.patch.object(bridge, "restart_gateway_if_running") as restart, mock.patch.object(
            bridge, "restore_internal_config_backup"
        ) as restore, mock.patch.object(bridge, "gateway_is_running", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "rolled back"):
                bridge.apply_lab_profile_transaction({}, {})
        restore.assert_called_once_with(backup)
        restart.assert_called_once_with(True)

    def test_gateway_activation_restores_original_running_state(self):
        with mock.patch.object(bridge, "gateway_is_running", return_value=False), mock.patch.object(
            bridge, "hermes_command", return_value={"output": "started"}
        ) as command:
            result = bridge.restart_gateway_if_running(True)
        command.assert_called_once_with("gateway", "start", timeout=90)
        self.assertEqual(result["status"], "restored_running")

        with mock.patch.object(bridge, "hermes_command") as command:
            self.assertEqual(
                bridge.restart_gateway_if_running(False)["status"], "preserved_stopped"
            )
        command.assert_not_called()

    def test_standalone_cron_action_bootstraps_installed_agency_import(self):
        package = ModuleType("agency")
        package.__path__ = []
        cron = ModuleType("agency.cron")
        cron.cron_action = lambda verb: f"ran {verb}"
        with mock.patch.dict(
            "sys.modules", {"agency": package, "agency.cron": cron}
        ), mock.patch.object(bridge, "import_agency") as bootstrap:
            result = bridge.execute_mutation("agency_run_cron", {})
        bootstrap.assert_called_once_with()
        self.assertEqual(result["result"]["output"], "ran run")


if __name__ == "__main__":
    unittest.main()
