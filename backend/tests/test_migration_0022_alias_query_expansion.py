from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_alias_index_dynasty_and_evidence_tables(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'alias-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0021_structured_search_filters")
        await asyncio.to_thread(_upgrade, config, "0022_alias_query_expansion")
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0022_alias_query_expansion"
        assert {"wu_alias_index", "wu_alias_dynasties", "wu_alias_evidence"} <= tables
    finally:
        await engine.dispose()
