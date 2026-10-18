import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_migration_preserves_existing_history_and_enforces_idempotency():
    path = Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations/versions/0045_map_reconstruction_jobs.py"
    spec = importlib.util.spec_from_file_location("reconstruction_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE existing_history (id INTEGER)"))
        connection.execute(text("INSERT INTO existing_history VALUES (1)"))
        revision.op = Operations(MigrationContext.configure(connection))
        revision.upgrade()
        indexes = inspect(connection).get_indexes("map_reconstruction_jobs")
        assert any(index["unique"] and index["column_names"] == ["owner_id", "request_key"] for index in indexes)
        revision.downgrade()
        assert connection.execute(text("SELECT id FROM existing_history")).scalar_one() == 1
        assert "map_reconstruction_jobs" not in inspect(connection).get_table_names()
    engine.dispose()
