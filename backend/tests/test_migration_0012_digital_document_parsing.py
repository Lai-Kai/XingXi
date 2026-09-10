from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_creates_parsed_document_and_ordered_block_tables(tmp_path):
    asyncio.run(_exercise_parsing_migration(tmp_path))


async def _exercise_parsing_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'parsing-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0011_file_deduplication")
        await asyncio.to_thread(_upgrade, config, "0012_digital_document_parsing")

        async with engine.connect() as connection:
            schema = await connection.run_sync(_inspect_schema)
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0012_digital_document_parsing"
        assert schema["parsed_document_columns"] >= {
            "id",
            "source_file_id",
            "parser_name",
            "parser_version",
            "mime_type",
            "page_count",
            "text",
            "metadata_json",
            "parsed_at",
        }
        assert schema["parsed_block_columns"] >= {
            "id",
            "parsed_document_id",
            "block_type",
            "page_number",
            "block_index",
            "text",
            "metadata_json",
        }
        assert {tuple(item["column_names"]) for item in schema["parsed_document_uniques"]} == {("source_file_id",)}
        assert {item["name"] for item in schema["parsed_block_checks"]} >= {
            "ck_wu_parsed_block_page_number",
            "ck_wu_parsed_block_index",
        }
        block_foreign_keys = {tuple(item["constrained_columns"]): item for item in schema["parsed_block_foreign_keys"]}
        assert block_foreign_keys[("parsed_document_id",)]["options"]["ondelete"] == "CASCADE"
    finally:
        await engine.dispose()


def _inspect_schema(connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "parsed_document_columns": {column["name"] for column in inspector.get_columns("wu_parsed_documents")},
        "parsed_block_columns": {column["name"] for column in inspector.get_columns("wu_parsed_blocks")},
        "parsed_document_uniques": inspector.get_unique_constraints("wu_parsed_documents"),
        "parsed_block_checks": inspector.get_check_constraints("wu_parsed_blocks"),
        "parsed_block_foreign_keys": inspector.get_foreign_keys("wu_parsed_blocks"),
    }
