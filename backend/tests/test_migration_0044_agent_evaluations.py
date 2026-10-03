from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def _revision(connection, filename):
    path = Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations/versions" / filename
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(connection))
    return module


def test_upgrade_is_repeatable_and_downgrade_preserves_manual_history():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        _revision(connection, "0028_operations_loop.py").upgrade()
        connection.execute(text("INSERT INTO wu_evaluation_runs(id,status,total,passed,pass_rate,created_by,created_at) VALUES ('legacy','completed',1,0,0,'operator','2026-09-26')"))
        revision = _revision(connection, "0044_agent_evaluations.py")
        revision.upgrade()
        revision.upgrade()
        assert connection.execute(text("SELECT execution_mode FROM wu_evaluation_runs WHERE id='legacy'")).scalar_one() == "manual"
        assert connection.execute(text("SELECT count(*) FROM wu_evaluation_worker")).scalar_one() == 1
        revision.downgrade()
        assert connection.execute(text("SELECT total FROM wu_evaluation_runs WHERE id='legacy'")).scalar_one() == 1
        assert "wu_evaluation_attempts" not in inspect(connection).get_table_names()
    engine.dispose()
