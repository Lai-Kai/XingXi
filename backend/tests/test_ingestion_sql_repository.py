from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import CopyrightStatus, SourceDocument, SourceFile, SourceLevel, SourceType
from wu_culture.ingestion import (
    IngestionConcurrencyError,
    IngestionIdempotencyConflict,
    IngestionJobStatus,
    IngestionStepName,
    IngestionStepStatus,
    begin_step,
    create_ingestion_job,
)
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


def test_ingestion_job_idempotency_events_optimistic_lock_and_recovery(tmp_path):
    asyncio.run(_exercise_repository(tmp_path))


async def _exercise_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ingestion.db'}")

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
    repository = SqlIngestionJobRepository(session_factory)
    await document_repository.create(
        SourceDocument(
            id="document-1",
            title="木渎小志",
            edition="测试版",
            source_type=SourceType.GAZETTEER,
            source_level=SourceLevel.A,
            copyright_status=CopyrightStatus.UNKNOWN,
            source_institution="测试机构",
            holder="测试机构",
            created_by="admin-1",
            created_at=NOW,
            updated_by="admin-1",
            updated_at=NOW,
        )
    )
    source_file = SourceFile(
        id="file-1",
        document_id="document-1",
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
            owner_id="document-1",
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
    job, created_event = create_ingestion_job(
        job_id="job-1",
        document_id="document-1",
        source_file_id="file-1",
        idempotency_key="upload:file-1:v1",
        created_by="admin-1",
        now=NOW,
    )

    try:
        stored, created = await repository.create(job, created_event)
        reused, created_again = await repository.create(job, created_event)
        assert created is True
        assert created_again is False
        assert reused == stored == job
        recent = await repository.list_recent()
        assert [(item[0].id, item[1], item[2]) for item in recent] == [("job-1", "木渎小志", "木渎小志.pdf")]
        context = await repository.get_with_context(job.id)
        assert context is not None
        assert context[1:] == ("木渎小志", "木渎小志.pdf")
        assert [item[0].id for item in await repository.list_recent(statuses={IngestionJobStatus.PENDING})] == ["job-1"]

        running, started_event = begin_step(stored, step_name=IngestionStepName.PARSE, worker_id="worker-1", now=NOW + timedelta(seconds=1))
        await repository.save(running, started_event, expected_version=stored.version)
        assert (await repository.get(job.id)) == running
        assert [event.event_type for event in await repository.list_events(job.id)] == ["job_created", "step_started"]

        with pytest.raises(IngestionConcurrencyError):
            await repository.save(running, started_event, expected_version=stored.version)

        recovered = await repository.recover_interrupted(now=NOW + timedelta(minutes=1))
        assert len(recovered) == 1
        assert recovered[0].step(IngestionStepName.PARSE).status is IngestionStepStatus.PENDING
        assert recovered[0].step(IngestionStepName.PARSE).attempt_count == 1
        assert (await repository.list_events(job.id))[-1].event_type == "job_recovered"

        second_job, second_event = create_ingestion_job(
            job_id="job-2",
            document_id="document-1",
            source_file_id="file-1",
            idempotency_key="upload:file-1:v2",
            created_by="admin-1",
            now=NOW + timedelta(minutes=2),
        )
        await repository.create(second_job, second_event)
        claims = await asyncio.gather(
            repository.try_start_step(
                job.id,
                step_name=IngestionStepName.PARSE,
                worker_id="worker-a",
                max_concurrent_jobs=1,
                lease_seconds=60,
                now=NOW + timedelta(minutes=3),
            ),
            repository.try_start_step(
                second_job.id,
                step_name=IngestionStepName.PARSE,
                worker_id="worker-b",
                max_concurrent_jobs=1,
                lease_seconds=60,
                now=NOW + timedelta(minutes=3),
            ),
        )
        assert sum(claim is not None for claim in claims) == 1
        claimed = next(claim for claim in claims if claim is not None)
        assert claimed.owner_worker_id in {"worker-a", "worker-b"}
        assert claimed.lease_expires_at == NOW + timedelta(minutes=4)
        assert (
            await repository.renew_lease(
                claimed.id,
                worker_id="another-worker",
                lease_seconds=60,
                now=NOW + timedelta(minutes=3, seconds=10),
            )
            is None
        )
        renewed = await repository.renew_lease(
            claimed.id,
            worker_id=claimed.owner_worker_id,
            lease_seconds=60,
            now=NOW + timedelta(minutes=3, seconds=10),
        )
        assert renewed is not None
        assert renewed.lease_expires_at == NOW + timedelta(minutes=4, seconds=10)
        assert await repository.recover_interrupted(now=NOW + timedelta(minutes=4)) == []
        expired = await repository.recover_interrupted(
            now=NOW + timedelta(minutes=4, seconds=21),
            grace_seconds=10,
        )
        assert [item.id for item in expired] == [claimed.id]
        assert expired[0].status.value == "pending"

        conflicting = job.model_copy(update={"source_file_id": "file-other"})
        with pytest.raises(IngestionIdempotencyConflict):
            await repository.create(conflicting, created_event)
    finally:
        await engine.dispose()
