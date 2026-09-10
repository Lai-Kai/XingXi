from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_vector_version_embedding_and_state_tables(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'vector-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0019_fulltext_search")
        await asyncio.to_thread(_upgrade, config, "0020_vector_search")
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))
            columns = await connection.run_sync(lambda sync: {column["name"]: str(column["type"]) for column in sa.inspect(sync).get_columns("wu_vector_embeddings")})
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0020_vector_search"
        assert {
            "wu_vector_index_versions",
            "wu_vector_embeddings",
            "wu_vector_index_states",
        } <= tables
        assert columns["embedding"] == "BLOB"
    finally:
        await engine.dispose()
