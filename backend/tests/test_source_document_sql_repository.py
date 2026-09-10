from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import CopyrightStatus, SourceDocument, SourceDocumentStatus, SourceLevel, SourceType

from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture import SourceDocumentRow, SqlSourceDocumentRepository


def test_source_document_metadata_survives_repository_recreation(tmp_path):
    asyncio.run(_exercise_repository_recreation(tmp_path))


async def _exercise_repository_recreation(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sources.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=[SourceDocumentRow.__table__]))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    document = SourceDocument(
        id="source-stable-id",
        title="震泽商会会员名录",
        edition="民国二十三年抄本",
        source_institution="私人授权收藏",
        source_type=SourceType.OTHER,
        source_type_label="商会名录",
        source_level=SourceLevel.A,
        holder="星羲项目资料组",
        status=SourceDocumentStatus.REGISTERED,
        copyright_status=CopyrightStatus.UNKNOWN,
        created_by="admin-1",
        created_at=now,
        updated_by="admin-1",
        updated_at=now,
    )
    try:
        await SqlSourceDocumentRepository(session_factory).create(document)

        recreated = SqlSourceDocumentRepository(session_factory)
        restored = await recreated.get(document.id)

        assert restored == document
        assert await recreated.list() == [document]
    finally:
        await engine.dispose()
