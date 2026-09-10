from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_backfills_existing_sources_to_default_deny(tmp_path):
    asyncio.run(_exercise_default_deny_backfill(tmp_path))


async def _exercise_default_deny_backfill(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'authorization-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0008_source_registration")
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO wu_source_documents "
                    "(id, title, edition, source_type, source_level, copyright_status, file_hash, "
                    "source_institution, holder, status, created_by, created_at, updated_by, updated_at) "
                    "VALUES ('legacy-source', 'Legacy title', NULL, 'archive', 'C', 'unknown', NULL, "
                    "'unknown', 'unknown', 'registered', NULL, NULL, NULL, NULL)"
                )
            )

        await asyncio.to_thread(_upgrade, config, "head")

        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    sa.text("SELECT authorization_status, visibility_scope, authorized_uses_json, authorization_basis, authorization_valid_until, authorization_proof_object_key FROM wu_source_documents WHERE id = 'legacy-source'")
                )
            ).one()
            tables = await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))
        assert tuple(row) == ("unconfirmed", "internal", "[]", None, None, None)
        assert "wu_source_authorization_events" in tables
    finally:
        await engine.dispose()
