from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_versioned_chunk_sets_and_structured_chunk_columns(tmp_path):
    asyncio.run(_exercise_chunking_migration(tmp_path))


async def _exercise_chunking_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'chunking-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0014_raw_clean_text")
        await asyncio.to_thread(_upgrade, config, "0015_structured_chunking")

        async with engine.connect() as connection:
            schema = await connection.run_sync(_inspect_schema)
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0015_structured_chunking"
        assert schema["set_columns"] >= {
            "document_id",
            "source_file_id",
            "split_version",
            "policy_json",
            "structure_json",
            "input_sha256",
            "generated_by",
            "generated_at",
        }
        assert {tuple(item["column_names"]) for item in schema["set_uniques"]} == {("source_file_id", "split_version")}
        assert schema["chunk_columns"] >= {
            "source_file_id",
            "chunk_set_id",
            "split_version",
            "chunk_index",
            "item",
            "paragraph_index",
            "paragraph_char_start",
            "paragraph_char_end",
            "cleaned_page_ids_json",
            "content_sha256",
        }
        assert {item["name"] for item in schema["chunk_checks"]} >= {
            "ck_wu_text_chunk_index",
            "ck_wu_text_chunk_char_range",
        }
        chunk_fks = {tuple(item["constrained_columns"]): item for item in schema["chunk_foreign_keys"]}
        assert chunk_fks[("chunk_set_id",)]["referred_table"] == "wu_chunk_sets"
        assert chunk_fks[("chunk_set_id",)]["options"]["ondelete"] == "CASCADE"
        source_file_fks = {tuple(item["constrained_columns"]): item for item in schema["source_file_foreign_keys"]}
        assert source_file_fks[("duplicate_of_file_id",)]["referred_table"] == "wu_source_files"
        assert source_file_fks[("version_of_file_id",)]["referred_table"] == "wu_source_files"
    finally:
        await engine.dispose()


def _inspect_schema(connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "set_columns": {column["name"] for column in inspector.get_columns("wu_chunk_sets")},
        "set_uniques": inspector.get_unique_constraints("wu_chunk_sets"),
        "chunk_columns": {column["name"] for column in inspector.get_columns("wu_text_chunks")},
        "chunk_checks": inspector.get_check_constraints("wu_text_chunks"),
        "chunk_foreign_keys": inspector.get_foreign_keys("wu_text_chunks"),
        "source_file_foreign_keys": inspector.get_foreign_keys("wu_source_files"),
    }
