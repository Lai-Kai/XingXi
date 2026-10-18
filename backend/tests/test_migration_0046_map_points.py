import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_custom_point_migration_upgrade_downgrade_preserves_existing_tables():
    path = Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations/versions/0046_custom_map_points.py"
    spec = importlib.util.spec_from_file_location("custom_point_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    assert revision.down_revision == "0045_map_reconstruction_jobs"
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE previous_history (id INTEGER)"))
        connection.execute(text("INSERT INTO previous_history VALUES (1)"))
        revision.op = Operations(MigrationContext.configure(connection))
        revision.upgrade()
        assert "map_custom_points" in inspect(connection).get_table_names()
        assert any(index["unique"] and index["column_names"] == ["owner_id", "request_key"] for index in inspect(connection).get_indexes("map_custom_points"))
        revision.downgrade()
        assert connection.execute(text("SELECT id FROM previous_history")).scalar_one() == 1
        assert "map_custom_points" not in inspect(connection).get_table_names()
    engine.dispose()
