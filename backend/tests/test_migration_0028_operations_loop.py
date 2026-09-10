from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = Path(__file__).parents[1] / "packages" / "harness" / "deerflow" / "persistence" / "migrations" / "versions" / "0028_operations_loop.py"


def test_operations_migration_creates_append_only_loop_tables() -> None:
    spec = importlib.util.spec_from_file_location("migration_0028", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        module.op = operations
        module.upgrade()
        tables = set(sa.inspect(connection).get_table_names())

    assert {
        "wu_operation_events",
        "wu_correction_records",
        "wu_evaluation_cases",
        "wu_evaluation_runs",
        "wu_evaluation_results",
        "wu_asset_versions",
    } <= tables
