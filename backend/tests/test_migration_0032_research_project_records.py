from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = (
    Path(__file__).parents[1]
    / "packages"
    / "harness"
    / "deerflow"
    / "persistence"
    / "migrations"
    / "versions"
    / "0032_research_project_records.py"
)


def test_research_project_records_migration_creates_durable_record_table() -> None:
    spec = importlib.util.spec_from_file_location("migration_0032", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "wu_research_projects",
        metadata,
        sa.Column("id", sa.String(255), primary_key=True),
    )
    with engine.begin() as connection:
        metadata.create_all(connection)
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()
        inspector = sa.inspect(connection)
        columns = {item["name"] for item in inspector.get_columns("wu_project_records")}
        foreign_keys = inspector.get_foreign_keys("wu_project_records")

    assert columns == {
        "id",
        "project_id",
        "kind",
        "content",
        "created_by",
        "created_at",
        "updated_at",
    }
    assert foreign_keys[0]["referred_table"] == "wu_research_projects"
    assert foreign_keys[0]["options"]["ondelete"] == "CASCADE"
