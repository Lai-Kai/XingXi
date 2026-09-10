from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from wu_culture import DocumentParseError, SourceFile
from wu_culture.ingestion import (
    IngestionJob,
    IngestionJobStatus,
    IngestionStepName,
    begin_step,
    create_ingestion_job,
)
from wu_culture.storage import ObjectKind, StoredObject, StoredObjectContent

from app.gateway.ingestion_worker import IngestionWorker


class _JobRepository:
    def __init__(self, job: IngestionJob) -> None:
        self.job = job

    async def list_recent(self, *, limit=100, statuses=None):  # noqa: ANN001, ARG002
        if statuses and self.job.status not in statuses:
            return []
        return [(self.job, "测试文献", "测试文献.txt")]

    async def try_start_step(self, job_id, *, step_name, worker_id, max_concurrent_jobs, lease_seconds, now):  # noqa: ANN001, ARG002
        if self.job.id != job_id or self.job.status is not IngestionJobStatus.PENDING or self.job.current_step is not step_name:
            return None
        self.job, _ = begin_step(
            self.job,
            step_name=step_name,
            worker_id=worker_id,
            lease_expires_at=now + timedelta(seconds=60),
            now=now,
        )
        return self.job

    async def get(self, job_id):  # noqa: ANN001
        return self.job if self.job.id == job_id else None

    async def save(self, job, event, *, expected_version):  # noqa: ANN001
        assert job.version == expected_version + 1
        self.job = job

    async def renew_lease(self, job_id, *, worker_id, lease_seconds, now):  # noqa: ANN001, ARG002
        return self.job if self.job.id == job_id else None


class _SourceFiles:
    def __init__(self, source_file: SourceFile) -> None:
        self.source_file = source_file

    async def get(self, source_file_id):  # noqa: ANN001
        return self.source_file if source_file_id == self.source_file.id else None


class _ObjectStorage:
    def __init__(self, source_file: SourceFile, content: bytes) -> None:
        metadata = StoredObject(
            object_key=source_file.object_key,
            owner_id=source_file.document_id,
            kind=ObjectKind.ORIGINAL,
            sha256=source_file.sha256,
            mime_type=source_file.mime_type,
            size=len(content),
            backend="test",
            storage_uri="memory://source",
            original_filename=source_file.original_filename,
            created_at=datetime.now(UTC),
        )
        self.stored = StoredObjectContent(metadata=metadata, content=content)

    async def get(self, *, owner_id, object_key):  # noqa: ANN001
        assert owner_id == self.stored.metadata.owner_id
        assert object_key == self.stored.metadata.object_key
        return self.stored


class _Parsed:
    def __init__(self) -> None:
        self.document = None
        self.save_count = 0

    async def get_by_source_file_id(self, source_file_id):  # noqa: ANN001
        return self.document if self.document is not None and self.document.source_file_id == source_file_id else None

    async def save(self, document):  # noqa: ANN001
        self.save_count += 1
        self.document = document


class _Ocr:
    def __init__(self) -> None:
        self.attempts = ()
        self.save_count = 0

    async def list_latest(self, source_file_id):  # noqa: ANN001
        return [attempt for attempt in self.attempts if attempt.source_file_id == source_file_id]

    async def save_attempts(self, attempts):  # noqa: ANN001
        self.save_count += 1
        self.attempts = tuple(attempts)


class _Cleaning:
    def __init__(self) -> None:
        self.pages = ()
        self.save_count = 0

    async def list_latest(self, source_file_id):  # noqa: ANN001
        return [page for page in self.pages if page.source_file_id == source_file_id]

    async def save_many(self, pages):  # noqa: ANN001
        self.save_count += 1
        self.pages = tuple(pages)


class _Chunks:
    def __init__(self) -> None:
        self.chunk_set = None
        self.save_count = 0

    async def get(self, source_file_id, split_version):  # noqa: ANN001
        if self.chunk_set is not None and self.chunk_set.source_file_id == source_file_id and self.chunk_set.policy.split_version == split_version:
            return self.chunk_set
        return None

    async def save(self, chunk_set):  # noqa: ANN001
        self.save_count += 1
        self.chunk_set = chunk_set

    async def list_all(self):
        return [self.chunk_set] if self.chunk_set is not None else []


class _Evidence:
    def __init__(self) -> None:
        self.calls = []

    async def ensure_chunk_evidence(self, *, chunk_set_id):
        self.calls.append(chunk_set_id)
        return 2


class _Graph:
    def __init__(self) -> None:
        self.chunk_ids = []

    async def ingest_chunk(self, **payload):  # noqa: ANN003
        self.chunk_ids.append(payload["chunk_id"])
        return 1


def _config(*, auto_publish_internal_release: bool = False):
    return SimpleNamespace(
        ingestion=SimpleNamespace(
            max_concurrent_jobs=2,
            lease_seconds=60,
            auto_publish_internal_release=auto_publish_internal_release,
        ),
        ocr=SimpleNamespace(render_dpi=150, max_pages_per_batch=50),
    )


def _worker(content: bytes, *, filename: str = "测试文献.txt", mime_type: str = "text/plain"):
    source_file = SourceFile(
        id="source-file-worker",
        document_id="source-document-worker",
        object_key="objects/source-worker",
        original_filename=filename,
        mime_type=mime_type,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by="admin",
        uploaded_at=datetime.now(UTC),
    )
    job, _ = create_ingestion_job(
        job_id="ingestion-job-worker",
        document_id=source_file.document_id,
        source_file_id=source_file.id,
        idempotency_key="upload:source-file-worker",
        created_by="admin",
        now=datetime.now(UTC),
    )
    jobs = _JobRepository(job)
    parsed = _Parsed()
    ocr = _Ocr()
    cleaning = _Cleaning()
    chunks = _Chunks()
    evidence = _Evidence()
    graph = _Graph()
    worker = IngestionWorker(
        job_repository=jobs,
        source_file_repository=_SourceFiles(source_file),
        parsed_repository=parsed,
        ocr_repository=ocr,
        cleaning_repository=cleaning,
        chunk_repository=chunks,
        evidence_repository=evidence,
        graph_repository=graph,
        object_storage=_ObjectStorage(source_file, content),
        object_metadata_repository=None,
        corpus_config=None,
        app_config=_config(),
        worker_id="test-worker",
    )
    return worker, jobs, parsed, ocr, cleaning, chunks, evidence, graph


@pytest.mark.asyncio
async def test_worker_processes_every_pipeline_step_and_stages_all_chunks() -> None:
    content = "卷一 山川\n目一 木渎\n永安桥位于木渎镇。\n\n木渎镇沿香溪而建。".encode()
    worker, jobs, parsed, ocr, cleaning, chunks, evidence, graph = _worker(content)

    while await worker.run_once():
        pass

    assert jobs.job.status is IngestionJobStatus.AWAITING_REVIEW
    assert jobs.job.current_step is IngestionStepName.REVIEW
    assert parsed.save_count == 1
    assert ocr.save_count == 1
    assert cleaning.save_count == 1
    assert chunks.save_count == 1
    assert chunks.chunk_set is not None
    assert len(chunks.chunk_set.chunks) >= 1
    assert evidence.calls == [chunks.chunk_set.id]
    assert graph.chunk_ids == [chunk.id for chunk in chunks.chunk_set.chunks]


@pytest.mark.asyncio
async def test_worker_reuses_all_derived_outputs_on_retry() -> None:
    content = "第一段记录木渎。\n\n第二段记录香溪。".encode()
    worker, jobs, parsed, ocr, cleaning, chunks, evidence, graph = _worker(content)

    while await worker.run_once():
        pass
    first_chunk_set = chunks.chunk_set
    first_graph_count = len(graph.chunk_ids)

    assert first_chunk_set is not None
    assert await worker._process_parse(jobs.job) == f"parsed:{parsed.document.id}"
    assert await worker._process_ocr(jobs.job) == "ocr-pages:1"
    assert (await worker._process_clean(jobs.job)).startswith("clean-pages:")
    assert (await worker._process_chunk(jobs.job)).startswith(f"chunk-set:{first_chunk_set.id}")

    assert parsed.save_count == 1
    assert ocr.save_count == 1
    assert cleaning.save_count == 1
    assert chunks.save_count == 1
    assert len(evidence.calls) == 2
    assert len(graph.chunk_ids) == first_graph_count * 2


@pytest.mark.asyncio
async def test_worker_marks_corrupt_pdf_as_non_retryable_failure() -> None:
    worker, jobs, _parsed, _ocr, _cleaning, _chunks, _evidence, _graph = _worker(
        b"%PDF-1.7\nnot a valid PDF",
        filename="broken.pdf",
        mime_type="application/pdf",
    )

    assert await worker.run_once() is True
    assert jobs.job.status is IngestionJobStatus.FAILED
    assert jobs.job.error_code == "invalid_pdf"
    assert jobs.job.step(IngestionStepName.PARSE).retryable is False


@pytest.mark.asyncio
async def test_worker_reports_scanned_pdf_without_ocr_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    # The parser's stable no-text result is enough to exercise the worker's
    # handoff to OCR without adding a PDF writer dependency to this test.
    def no_text_layer(_request):  # noqa: ANN001
        raise DocumentParseError("no_extractable_text", "PDF has no extractable text")

    monkeypatch.setattr("app.gateway.ingestion_worker.parse_document", no_text_layer)
    content = b"scanned-pdf-placeholder"
    worker, jobs, *_ = _worker(content, filename="scan.pdf", mime_type="application/pdf")

    assert await worker.run_once() is True
    assert jobs.job.current_step is IngestionStepName.OCR
    assert await worker.run_once() is True
    assert jobs.job.status is IngestionJobStatus.FAILED
    assert "OCR service is not configured" in (jobs.job.error_message or "")
