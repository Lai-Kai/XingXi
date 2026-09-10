from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_page_review_status_and_append_only_review_records(tmp_path):
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'review-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0016_ingestion_jobs")
        await asyncio.to_thread(_upgrade, config, "0017_text_review")

        async with engine.connect() as connection:
            schema = await connection.run_sync(_inspect_schema)
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0017_text_review"
        assert "review_status" in schema["cleaned_page_columns"]
        assert schema["record_columns"] >= {
            "document_id",
            "source_file_id",
            "target_type",
            "target_id",
            "revision",
            "previous_status",
            "decision",
            "comment",
            "batch_id",
            "reviewed_by",
            "reviewed_at",
        }
        assert {tuple(item["column_names"]) for item in schema["record_uniques"]} == {("target_type", "target_id", "revision")}
        assert {tuple(item["constrained_columns"]) for item in schema["record_fks"]} == {("document_id",), ("source_file_id",)}
        assert {item["name"] for item in schema["record_checks"]} >= {
            "ck_wu_review_record_revision",
            "ck_wu_review_record_target_type",
            "ck_wu_review_record_decision",
        }
    finally:
        await engine.dispose()


def _inspect_schema(connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "cleaned_page_columns": {column["name"] for column in inspector.get_columns("wu_cleaned_ocr_pages")},
        "record_columns": {column["name"] for column in inspector.get_columns("wu_review_records")},
        "record_uniques": inspector.get_unique_constraints("wu_review_records"),
        "record_fks": inspector.get_foreign_keys("wu_review_records"),
        "record_checks": inspector.get_check_constraints("wu_review_records"),
    }
