from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture.storage import ObjectKind, PutObjectRequest

from deerflow.object_storage import LocalObjectStorage
from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow, SqlObjectMetadataRepository


def test_sql_repository_persists_metadata_without_file_bytes(tmp_path):
    asyncio.run(_exercise_metadata_repository(tmp_path))


async def _exercise_metadata_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'metadata.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=[ObjectMetadataRow.__table__]))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        content = b"historical source bytes stay outside SQL"
        metadata = await LocalObjectStorage(tmp_path / "objects").put(
            PutObjectRequest(
                owner_id="researcher-1",
                kind=ObjectKind.ORIGINAL,
                content=content,
                mime_type="application/pdf",
                original_filename="source.pdf",
            )
        )
        await SqlObjectMetadataRepository(session_factory).save(metadata)

        restored = await SqlObjectMetadataRepository(session_factory).get(
            owner_id="researcher-1",
            object_key=metadata.object_key,
        )

        assert restored == metadata
        assert "content" not in ObjectMetadataRow.__table__.columns
        assert "bytes" not in ObjectMetadataRow.__table__.columns
    finally:
        await engine.dispose()
