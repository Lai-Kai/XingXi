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
    IngestionEventRow,
    IngestionJobRow,
    IngestionStepRow,
    SourceDocumentRow,
    SourceFileRow,
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
                tables=[
                    SourceDocumentRow.__table__,
                    ObjectMetadataRow.__table__,
                    SourceFileRow.__table__,
                    IngestionJobRow.__table__,
                    IngestionStepRow.__table__,
                    IngestionEventRow.__table__,
                ],
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
