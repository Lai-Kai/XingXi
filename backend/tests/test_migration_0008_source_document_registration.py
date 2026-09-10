from __future__ import annotations

import asyncio
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_all_revision_ids_fit_alembic_version_column():
    migrations_dir = Path(__file__).resolve().parents[1] / "packages" / "harness" / "deerflow" / "persistence" / "migrations"
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    revisions = ScriptDirectory.from_config(config).walk_revisions()

    assert all(len(revision.revision) <= 32 for revision in revisions)


def test_migration_backfills_existing_source_rows(tmp_path):
    asyncio.run(_exercise_backfill(tmp_path))


async def _exercise_backfill(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0007_object_storage_metadata")
        async with engine.begin() as connection:
            await connection.execute(sa.text("INSERT INTO wu_source_documents (id, title, edition, source_type, source_level, copyright_status, file_hash) VALUES ('legacy-source', 'Legacy title', NULL, 'archive', 'C', 'unknown', NULL)"))

        await asyncio.to_thread(_upgrade, config, "head")

        async with engine.connect() as connection:
            row = (await connection.execute(sa.text("SELECT source_institution, holder, status, created_by, created_at, updated_by, updated_at FROM wu_source_documents WHERE id = 'legacy-source'"))).one()
        assert tuple(row) == ("unknown", "unknown", "registered", None, None, None, None)
    finally:
        await engine.dispose()
