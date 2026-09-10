from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.vector_extension import register_sqlite_vec


def test_sqlite_vec_loads_on_aiosqlite_and_partitions_knn(tmp_path) -> None:
    asyncio.run(_exercise_adapter(tmp_path))


async def _exercise_adapter(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'vectors.db'}")
    register_sqlite_vec(engine)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE VIRTUAL TABLE vectors USING vec0(index_version_id TEXT PARTITION KEY, embedding FLOAT[3] DISTANCE_METRIC=cosine)"))
            await connection.execute(
                text("INSERT INTO vectors(rowid, index_version_id, embedding) VALUES (:rowid, :version, :embedding)"),
                [
                    {"rowid": 1, "version": "v1", "embedding": "[1,0,0]"},
                    {"rowid": 2, "version": "v1", "embedding": "[0.8,0.2,0]"},
                    {"rowid": 3, "version": "v2", "embedding": "[1,0,0]"},
                ],
            )
            rows = (
                await connection.execute(
                    text("SELECT rowid, distance FROM vectors WHERE embedding MATCH :query AND k = :k AND index_version_id = :version"),
                    {"query": "[1,0,0]", "k": 2, "version": "v1"},
                )
            ).all()

        assert [row.rowid for row in rows] == [1, 2]
        assert all(row.rowid != 3 for row in rows)
        assert rows[0].distance == 0.0
    finally:
        await engine.dispose()
