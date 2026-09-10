from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_release_documents_and_sqlite_trigram_fts(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fulltext-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0018_knowledge_releases")
        await asyncio.to_thread(_upgrade, config, "0019_fulltext_search")
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()
            await connection.execute(sa.text("INSERT INTO wu_fulltext_fts(rowid, search_title, search_headings, search_body) VALUES (1, '', '', '木渎香溪沿岸古桥')"))
            match = (await connection.execute(sa.text("SELECT rowid FROM wu_fulltext_fts WHERE wu_fulltext_fts MATCH :query"), {"query": '"香溪沿岸"'})).scalar_one()

        assert version == "0019_fulltext_search"
        assert {"wu_fulltext_documents", "wu_fulltext_index_states", "wu_fulltext_fts"} <= tables
        assert match == 1
    finally:
        await engine.dispose()
