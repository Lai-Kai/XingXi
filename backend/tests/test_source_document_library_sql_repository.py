from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import CopyrightStatus, SourceDocument, SourceDocumentStatus, SourceFile, SourceLevel, SourceType
from wu_culture.ingestion import create_ingestion_job
from wu_culture.storage import ObjectKind, StoredObject

from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture import (
    WU_CULTURE_TABLES,
    IngestionJobRow,
    SqlIngestionJobRepository,
    SqlSourceDocumentRepository,
    SqlSourceFileRepository,
)

NOW = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)


def test_library_page_batches_files_and_returns_latest_job(tmp_path):
    asyncio.run(_exercise_library_page(tmp_path))


async def _exercise_library_page(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'library.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[*WU_CULTURE_TABLES, ObjectMetadataRow.__table__],
            )
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    document_repository = SqlSourceDocumentRepository(session_factory)
    file_repository = SqlSourceFileRepository(session_factory)
    job_repository = SqlIngestionJobRepository(session_factory)

    document = SourceDocument(
        id="document-1",
        title="木渎小志",
        edition="测试版",
        source_type=SourceType.GAZETTEER,
        source_level=SourceLevel.A,
        copyright_status=CopyrightStatus.UNKNOWN,
        source_institution="测试机构",
        holder="测试机构",
        status=SourceDocumentStatus.REGISTERED,
        created_by="admin-1",
        created_at=NOW,
        updated_by="admin-1",
        updated_at=NOW,
    )
    await document_repository.create(document)

    source_file = SourceFile(
        id="file-1",
        document_id=document.id,
        object_key="sources/document-1/file-1.pdf",
        original_filename="木渎小志.pdf",
        sha256="a" * 64,
        mime_type="application/pdf",
        size=100,
        uploaded_by="admin-1",
        uploaded_at=NOW,
    )
    await file_repository.attach(
        source_file,
        StoredObject(
            object_key=source_file.object_key,
            owner_id=document.id,
            kind=ObjectKind.ORIGINAL,
            sha256=source_file.sha256,
            mime_type=source_file.mime_type,
            size=source_file.size,
            backend="local",
            storage_uri="file:///objects/file-1.pdf",
            original_filename=source_file.original_filename,
            created_at=NOW,
        ),
    )

    for index, created_at in enumerate((NOW, NOW + timedelta(minutes=1)), start=1):
        job, event_record = create_ingestion_job(
            job_id=f"job-{index}",
            document_id=document.id,
            source_file_id=source_file.id,
            idempotency_key=f"upload:file-1:v{index}",
            created_by="admin-1",
            now=created_at,
        )
        await job_repository.create(job, event_record)

    items, total = await document_repository.list_library_page(limit=10, offset=0)

    assert total == 1
    assert len(items) == 1
    assert items[0].document.id == document.id
    assert len(items[0].files) == 1
    assert items[0].files[0].file.id == source_file.id
    assert items[0].files[0].ingestion_job is not None
    assert items[0].files[0].ingestion_job.id == "job-2"

    await engine.dispose()


def test_library_review_status_tracks_exact_latest_chunks_and_pages_independently_of_job(tmp_path):
    asyncio.run(_exercise_library_review(tmp_path))


async def _exercise_library_review(tmp_path):
    import json

    from sqlalchemy import insert, update
    from test_text_review_sql_repository import _seed_review_targets
    from wu_culture import ReviewStatus
    from wu_culture.review import ReviewBatchRequest, ReviewRequest, ReviewTargetType

    from deerflow.persistence.wu_culture import WU_CULTURE_TABLES, ChunkSetRow, CleanedOcrPageRow, SqlReviewRepository, TextChunkRow

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'library-review.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[*WU_CULTURE_TABLES, ObjectMetadataRow.__table__]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await _seed_review_targets(factory)
    job, event_record = create_ingestion_job(job_id="job-failed", document_id="document-1", source_file_id="file-1", idempotency_key="test-job", created_by="admin-1", now=NOW)
    await SqlIngestionJobRepository(factory).create(job, event_record)
    async with factory.begin() as session:
        await session.execute(update(IngestionJobRow).where(IngestionJobRow.id == job.id).values(status="failed", error_code="index_failed", error_message="temporary failure"))
    repository = SqlSourceDocumentRepository(factory)

    async def current():
        items, _ = await repository.list_library_page()
        item = items[0].files[0]
        assert item.ingestion_job.status.value == "failed"
        return item

    try:
        assert (await current()).review_status is ReviewStatus.PENDING
        review = SqlReviewRepository(factory)
        await review.review_many(
            document_id="document-1",
            source_file_id="file-1",
            batch=ReviewBatchRequest(
                items=(ReviewRequest(target_type=ReviewTargetType.PAGE, target_id="cleaned-page-1", decision=ReviewStatus.REVIEWED), ReviewRequest(target_type=ReviewTargetType.CHUNK, target_id="chunk-1", decision=ReviewStatus.REVIEWED))
            ),
            reviewed_by="admin-1",
            reviewed_at=NOW,
            batch_id="library-review",
        )
        assert (await current()).review_status is ReviewStatus.REVIEWED
        async with factory.begin() as session:
            page = await session.get(CleanedOcrPageRow, "cleaned-page-1")
            page_values = {column.name: getattr(page, column.name) for column in CleanedOcrPageRow.__table__.columns}
            await session.execute(insert(CleanedOcrPageRow), [{**page_values, "id": "unused-new-page", "generation_number": 2, "review_status": "pending"}])
        assert (await current()).review_status is ReviewStatus.REVIEWED
        async with factory.begin() as session:
            chunk_set = await session.get(ChunkSetRow, "chunk-set-1")
            values = {column.name: getattr(chunk_set, column.name) for column in ChunkSetRow.__table__.columns}
            await session.execute(insert(ChunkSetRow), [{**values, "id": "chunk-set-2", "split_version": "split-v2", "generated_at": NOW + timedelta(days=1)}])
            chunk = await session.get(TextChunkRow, "chunk-1")
            values = {column.name: getattr(chunk, column.name) for column in TextChunkRow.__table__.columns}
            await session.execute(insert(TextChunkRow), [{**values, "id": "chunk-2", "chunk_set_id": "chunk-set-2", "split_version": "split-v2", "review_status": "pending"}])
        assert (await current()).chunk_set_id == "chunk-set-2"
        assert (await current()).review_status is ReviewStatus.PENDING
        async with factory.begin() as session:
            await session.execute(update(TextChunkRow).where(TextChunkRow.id == "chunk-2").values(review_status="reviewed"))
            await session.execute(update(CleanedOcrPageRow).where(CleanedOcrPageRow.id == "cleaned-page-1").values(review_status="disputed"))
        assert (await current()).review_status is ReviewStatus.DISPUTED
        async with factory.begin() as session:
            await session.execute(update(CleanedOcrPageRow).where(CleanedOcrPageRow.id == "cleaned-page-1").values(review_status="rejected"))
        assert (await current()).review_status is ReviewStatus.REJECTED
        async with factory.begin() as session:
            await session.execute(update(CleanedOcrPageRow).where(CleanedOcrPageRow.id == "cleaned-page-1").values(review_status="reviewed"))
            await session.execute(update(TextChunkRow).where(TextChunkRow.id == "chunk-2").values(cleaned_page_ids_json=json.dumps(["missing-page"])))
        assert (await current()).review_status is ReviewStatus.PENDING
    finally:
        await engine.dispose()
