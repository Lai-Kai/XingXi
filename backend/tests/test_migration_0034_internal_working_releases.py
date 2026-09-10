from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_0034_adds_release_scope(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0033_fuxianzhi_corpus_import")
        await asyncio.to_thread(_upgrade, config, "0034_internal_working_releases")
        async with engine.connect() as connection:
            columns = await connection.run_sync(lambda sync: {column["name"]: column for column in sa.inspect(sync).get_columns("wu_knowledge_releases")})
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()
        assert version == "0034_internal_working_releases"
        assert columns["scope"]["nullable"] is False
    finally:
        await engine.dispose()
