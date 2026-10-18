"""Question storage must not replace legacy cases or historical batch data."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_upgrade_repeats_and_downgrade_keeps_manual_cases_and_run_history():
    engine = create_engine("sqlite://")
    directory = Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations/versions"
    try:
        with engine.begin() as connection:
            modules = []
            for filename in ("0028_operations_loop.py", "0044_agent_evaluations.py", "0046_agent_evaluation_cases.py"):
                spec = importlib.util.spec_from_file_location(filename[:-3], directory / filename)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.op = Operations(MigrationContext.configure(connection))
                module.upgrade()
                modules.append(module)
            tables_before = set(inspect(connection).get_table_names())
            connection.exec_driver_sql("INSERT INTO wu_evaluation_cases (id,name,question,expected_status,created_by,created_at) VALUES ('manual','人工题','保留原问题','answered','admin',CURRENT_TIMESTAMP)")
            connection.exec_driver_sql(
                "INSERT INTO wu_evaluation_runs (id,status,total,passed,created_by,created_at,execution_mode,spec_json) VALUES ('historical','completed',1,0,'admin',CURRENT_TIMESTAMP,'replay','{\"cases\":[{\"id\":\"grounded-pro\"}]}')"
            )
            manual_before = connection.exec_driver_sql("SELECT * FROM wu_evaluation_cases").all()
            history_before = connection.exec_driver_sql("SELECT * FROM wu_evaluation_runs").all()
            connection.exec_driver_sql("INSERT INTO wu_agent_evaluation_cases (case_id,active,created_by,created_at,updated_by,updated_at) VALUES ('grounded-pro',0,'admin',CURRENT_TIMESTAMP,'admin',CURRENT_TIMESTAMP)")
            modules[-1].upgrade()
            assert connection.exec_driver_sql("SELECT active FROM wu_agent_evaluation_cases").scalar_one() == 0
            assert connection.exec_driver_sql("SELECT * FROM wu_evaluation_cases").all() == manual_before
            assert connection.exec_driver_sql("SELECT * FROM wu_evaluation_runs").all() == history_before
            modules[-1].downgrade()
            assert set(inspect(connection).get_table_names()) == tables_before - {"wu_agent_evaluation_cases"}
            assert connection.exec_driver_sql("SELECT * FROM wu_evaluation_cases").all() == manual_before
            assert connection.exec_driver_sql("SELECT * FROM wu_evaluation_runs").all() == history_before
    finally:
        engine.dispose()
