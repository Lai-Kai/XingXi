from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture.chunking import ChunkingPolicy, ChunkSet, ChunkSourcePage, chunk_cleaned_pages

from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture import ChunkSetRow, SourceDocumentRow, SourceFileRow, SqlStructuredChunkRepository, TextChunkRow


def test_chunk_set_round_trips_structure_policy_and_stable_chunks(tmp_path):
    asyncio.run(_exercise_chunk_set_repository(tmp_path))


async def _exercise_chunk_set_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'chunks.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[SourceDocumentRow.__table__, SourceFileRow.__table__, ChunkSetRow.__table__, TextChunkRow.__table__],
            )
        )
    repository = SqlStructuredChunkRepository(async_sessionmaker(engine, expire_on_commit=False))
    page = ChunkSourcePage(
        cleaned_page_id="cleaned-page-1-g1",
        page_number=1,
        raw_text="卷一\n目一\n木渎沿河。",
        clean_text="卷一\n目一\n木渎沿河。",
    )
    policy = ChunkingPolicy(split_version="structure-v1", max_characters=200, overlap_characters=20)
    result = chunk_cleaned_pages(document_id="source-1", source_file_id="file-1", pages=(page,), policy=policy)
    chunk_set = ChunkSet(
        id="chunk-set-file-1-structure-v1",
        input_sha256=hashlib.sha256(page.clean_text.encode()).hexdigest(),
        generated_by="admin-1",
        generated_at=datetime.now(UTC),
        **result.model_dump(),
    )

    try:
        await repository.save(chunk_set)

        assert await repository.get("file-1", "structure-v1") == chunk_set
        assert await repository.list_versions("file-1") == [chunk_set]
    finally:
        await engine.dispose()
