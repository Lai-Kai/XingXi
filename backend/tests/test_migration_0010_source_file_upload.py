from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_creates_source_file_bindings(tmp_path):
    asyncio.run(_exercise_source_file_migration(tmp_path))


async def _exercise_source_file_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source-file-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0009_source_authorization")
        await asyncio.to_thread(_upgrade, config, "0010_source_file_upload")

        async with engine.connect() as connection:
            schema = await connection.run_sync(
                lambda sync: {
                    "tables": set(sa.inspect(sync).get_table_names()),
                    "columns": {column["name"] for column in sa.inspect(sync).get_columns("wu_source_files")},
                    "foreign_keys": {tuple(foreign_key["constrained_columns"]): foreign_key["referred_table"] for foreign_key in sa.inspect(sync).get_foreign_keys("wu_source_files")},
                }
            )
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0010_source_file_upload"
        assert "wu_source_files" in schema["tables"]
        assert schema["columns"] == {
            "id",
            "document_id",
            "object_key",
            "original_filename",
            "mime_type",
            "size",
            "uploaded_by",
            "uploaded_at",
        }
        assert schema["foreign_keys"][("document_id",)] == "wu_source_documents"
        assert schema["foreign_keys"][("object_key",)] == "wu_object_metadata"
    finally:
        await engine.dispose()
