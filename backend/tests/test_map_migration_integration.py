"""Both map and existing local migrations must remain upgradeable."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.base import Base


def test_future_autogeneration_preserves_map_tables(tmp_path):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{tmp_path / 'autogen.db'}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{tmp_path / 'autogen.db'}")
    names = {"map_reconstruction_jobs", "map_custom_points"}
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"include_object": lambda obj, name, type_, reflected, compare_to: type_ != "table" or name in names})
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("previous_head", ["base", "0046_agent_evaluation_cases", "0046_custom_map_points"])
def test_map_integration_upgrades_both_histories_without_losing_rows(tmp_path, previous_head):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}")
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    try:
        command.upgrade(config, previous_head)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE integration_history (id INTEGER PRIMARY KEY, note TEXT)"))
            connection.execute(text("INSERT INTO integration_history VALUES (1, 'preserve me')"))
            if previous_head == "0046_custom_map_points":
                connection.execute(text("INSERT INTO map_custom_points VALUES ('saved-point', 'admin', 'request-1', '原有点位', 120.5, 31.25, '2026-10-18')"))
            elif previous_head == "0046_agent_evaluation_cases":
                connection.execute(text("INSERT INTO wu_agent_evaluation_cases (case_id, active, created_by, created_at, updated_by, updated_at) VALUES ('saved-case', 1, 'admin', '2026-10-18', 'admin', '2026-10-18')"))
        command.upgrade(config, "head")
        with engine.begin() as connection:
            heads = ScriptDirectory.from_config(config).get_heads()
            assert heads == ["0047_merge_map_reconstruction"]
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == heads
            assert connection.execute(text("SELECT note FROM integration_history")).scalar_one() == "preserve me"
            assert {"map_reconstruction_jobs", "map_custom_points", "wu_agent_evaluation_cases"} <= set(inspect(connection).get_table_names())
            assert "ix_wu_evidence_chunk_document" in {index["name"] for index in inspect(connection).get_indexes("wu_evidence")}
            if previous_head == "0046_custom_map_points":
                assert connection.execute(text("SELECT name FROM map_custom_points WHERE id = 'saved-point'")).scalar_one() == "原有点位"
            elif previous_head == "0046_agent_evaluation_cases":
                assert connection.execute(text("SELECT active FROM wu_agent_evaluation_cases WHERE case_id = 'saved-case'")).scalar_one() == 1
    finally:
        engine.dispose()
