from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_creates_raw_clean_generation_and_change_tables(tmp_path):
    asyncio.run(_exercise_cleaning_migration(tmp_path))


async def _exercise_cleaning_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cleaning-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0013_scanned_source_ocr")
        await asyncio.to_thread(_upgrade, config, "0014_raw_clean_text")

        async with engine.connect() as connection:
            schema = await connection.run_sync(_inspect_schema)
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0014_raw_clean_text"
        assert schema["page_columns"] >= {
            "source_file_id",
            "ocr_attempt_id",
            "page_number",
            "generation_number",
            "raw_text",
            "raw_sha256",
            "clean_text",
            "clean_sha256",
            "rule_version",
            "script_conversion",
            "policy_json",
            "generated_by",
            "generated_at",
        }
        assert {tuple(item["column_names"]) for item in schema["page_uniques"]} == {("source_file_id", "page_number", "generation_number")}
        assert {item["name"] for item in schema["change_checks"]} >= {
            "ck_wu_text_cleaning_change_raw_range",
            "ck_wu_text_cleaning_change_clean_range",
        }
        change_fks = {tuple(item["constrained_columns"]): item for item in schema["change_foreign_keys"]}
        assert change_fks[("cleaned_page_id",)]["options"]["ondelete"] == "CASCADE"
    finally:
        await engine.dispose()


def _inspect_schema(connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "page_columns": {column["name"] for column in inspector.get_columns("wu_cleaned_ocr_pages")},
        "page_uniques": inspector.get_unique_constraints("wu_cleaned_ocr_pages"),
        "change_checks": inspector.get_check_constraints("wu_text_cleaning_changes"),
        "change_foreign_keys": inspector.get_foreign_keys("wu_text_cleaning_changes"),
    }
