"""SQLite to PostgreSQL migration safety contracts."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "migrate_sqlite_to_postgres.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("migrate_sqlite_to_postgres", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_plan_excludes_sqlite_fts_and_langgraph_internal_tables(tmp_path):
    module = _load_module()
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE checkpoints (thread_id TEXT)")
        conn.execute("CREATE TABLE checkpoint_writes (thread_id TEXT)")
        conn.execute("CREATE TABLE store (prefix TEXT)")
        conn.execute("CREATE VIRTUAL TABLE wu_fulltext_fts USING fts5(content)")

    inventory = module.inspect_sqlite(database)

    assert inventory.application_tables == ("users",)
    assert inventory.checkpointer_tables == ("checkpoints", "checkpoint_writes")
    assert inventory.store_tables == ("store",)
    assert "wu_fulltext_fts" in inventory.excluded_tables
    assert all(not name.startswith("wu_fulltext_fts_") for name in inventory.application_tables)


def test_dry_run_reports_source_counts_without_postgres(tmp_path):
    module = _load_module()
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO users (id) VALUES (?)", [("one",), ("two",)])
        conn.execute("CREATE TABLE checkpoints (thread_id TEXT)")
        conn.execute("INSERT INTO checkpoints (thread_id) VALUES ('thread-1')")

    report = module.build_dry_run_report(database)

    assert report["mode"] == "dry-run"
    assert report["source"]["application_counts"] == {"users": 2}
    assert report["source"]["checkpointer_counts"] == {"checkpoints": 1}
    assert report["source"]["total_application_rows"] == 2


def test_only_pristine_release_state_seed_can_be_removed():
    module = _load_module()

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _Connection:
        def __init__(self, rows):
            self.rows = rows
            self.deleted = False

        def execute(self, statement):
            if statement.lstrip().startswith("SELECT"):
                return _Result(self.rows)
            self.deleted = True
            return _Result([])

    pristine = _Connection([("active", None, 0, None, None)])
    module._remove_known_bootstrap_seeds(pristine)
    assert pristine.deleted is True

    modified = _Connection([("active", "release-1", 3, "admin", None)])
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        module._remove_known_bootstrap_seeds(modified)
    assert modified.deleted is False
