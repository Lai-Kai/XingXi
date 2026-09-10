from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_ingestion_jobs_steps_and_append_only_events(tmp_path):
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ingestion-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0015_structured_chunking")
        await asyncio.to_thread(_upgrade, config, "0016_ingestion_jobs")

        async with engine.connect() as connection:
            schema = await connection.run_sync(_inspect_schema)
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0016_ingestion_jobs"
        assert schema["job_columns"] >= {
            "document_id",
            "source_file_id",
            "idempotency_key",
            "status",
            "current_step",
            "progress_percent",
            "owner_worker_id",
            "lease_expires_at",
            "version",
            "event_sequence",
        }
        assert {tuple(item["column_names"]) for item in schema["job_uniques"]} == {("created_by", "idempotency_key")}
        assert {tuple(item["constrained_columns"]) for item in schema["job_fks"]} == {("document_id",), ("source_file_id",)}
        assert schema["step_pk"] == {"job_id", "name"}
        assert schema["event_pk"] == {"job_id", "sequence"}
        assert schema["step_fks"][("job_id",)]["options"]["ondelete"] == "CASCADE"
        assert schema["event_fks"][("job_id",)]["options"]["ondelete"] == "CASCADE"
    finally:
        await engine.dispose()


def _inspect_schema(connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "job_columns": {column["name"] for column in inspector.get_columns("wu_ingestion_jobs")},
        "job_uniques": inspector.get_unique_constraints("wu_ingestion_jobs"),
        "job_fks": inspector.get_foreign_keys("wu_ingestion_jobs"),
        "step_pk": set(inspector.get_pk_constraint("wu_ingestion_steps")["constrained_columns"]),
        "event_pk": set(inspector.get_pk_constraint("wu_ingestion_events")["constrained_columns"]),
        "step_fks": {tuple(item["constrained_columns"]): item for item in inspector.get_foreign_keys("wu_ingestion_steps")},
        "event_fks": {tuple(item["constrained_columns"]): item for item in inspector.get_foreign_keys("wu_ingestion_events")},
    }
