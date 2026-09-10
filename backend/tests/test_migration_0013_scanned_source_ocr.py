from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_creates_append_only_ocr_attempt_and_region_tables(tmp_path):
    asyncio.run(_exercise_ocr_migration(tmp_path))


async def _exercise_ocr_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ocr-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0012_digital_document_parsing")
        await asyncio.to_thread(_upgrade, config, "0013_scanned_source_ocr")

        async with engine.connect() as connection:
            schema = await connection.run_sync(_inspect_schema)
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0013_scanned_source_ocr"
        assert schema["attempt_columns"] >= {
            "id",
            "source_file_id",
            "page_number",
            "attempt_number",
            "image_sha256",
            "provider_name",
            "model_name",
            "languages_json",
            "status",
            "raw_text",
            "mean_confidence",
            "rotation_degrees",
            "error_code",
            "error_message",
            "created_at",
        }
        assert {tuple(item["column_names"]) for item in schema["attempt_uniques"]} == {("source_file_id", "page_number", "attempt_number")}
        assert {item["name"] for item in schema["region_checks"]} >= {"ck_wu_ocr_region_confidence", "ck_wu_ocr_region_bounds"}
        region_foreign_keys = {tuple(item["constrained_columns"]): item for item in schema["region_foreign_keys"]}
        assert region_foreign_keys[("attempt_id",)]["options"]["ondelete"] == "CASCADE"
    finally:
        await engine.dispose()


def _inspect_schema(connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "attempt_columns": {column["name"] for column in inspector.get_columns("wu_ocr_page_attempts")},
        "attempt_uniques": inspector.get_unique_constraints("wu_ocr_page_attempts"),
        "region_checks": inspector.get_check_constraints("wu_ocr_regions"),
        "region_foreign_keys": inspector.get_foreign_keys("wu_ocr_regions"),
    }
