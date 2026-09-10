from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from PIL import Image
from wu_culture import ReviewStatus
from wu_culture.ingestion import IngestionStepName, begin_step, complete_step
from wu_culture.repositories import InMemorySourceDocumentRepository, InMemorySourceFileRepository
from wu_culture.review import (
    PublicationGateDecision,
    ReviewChunkTarget,
    ReviewPageTarget,
    ReviewQueue,
    ReviewTargetType,
    build_review_record,
    evaluate_publication_gate,
)

from app.gateway.auth.models import User
from app.gateway.routers import source_documents
from deerflow.object_storage import LocalObjectStorage


def _user(role: str = "admin") -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email=f"{role}@example.com",
        password_hash="x",
        system_role=role,
    )


class _InMemoryIngestionRepository:
    def __init__(self):
        self.jobs = {}

    async def create(self, job, _event):
        self.jobs[job.id] = job
        return job, True

    async def get(self, job_id):
        return self.jobs.get(job_id)

    async def save(self, job, _event, *, expected_version):
        assert self.jobs[job.id].version == expected_version
        self.jobs[job.id] = job

    async def list_for_source_file(self, source_file_id):
        return [job for job in self.jobs.values() if job.source_file_id == source_file_id]

    async def list_events(self, job_id, *, after_sequence=0):
        return []


class _InMemoryReviewRepository:
    def __init__(self, *, document_id: str, source_file_id: str):
        self.queue = ReviewQueue(
            document_id=document_id,
            source_file_id=source_file_id,
            chunk_set_id="chunk-set-1",
            split_version="split-v1",
            pages=(
                ReviewPageTarget(
                    id="cleaned-page-1",
                    page_number=1,
                    generation_number=1,
                    raw_text="後臺",
                    clean_text="后台",
                    review_status=ReviewStatus.PENDING,
                    ocr_confidence=0.96,
                    rotation_degrees=0,
                    cleaning_change_count=2,
                ),
            ),
            chunks=(
                ReviewChunkTarget(
                    id="chunk-1",
                    chunk_index=0,
                    volume="卷一",
                    item="目一",
                    raw_text="後臺",
                    clean_text="后台",
                    page_start=1,
                    page_end=1,
                    cleaned_page_ids=("cleaned-page-1",),
                    review_status=ReviewStatus.PENDING,
                ),
            ),
        )
        self.records = []

    async def get_queue(self, *, source_file_id, chunk_set_id):
        assert source_file_id == self.queue.source_file_id
        assert chunk_set_id == self.queue.chunk_set_id
        return self.queue

    async def review_many(self, *, document_id, source_file_id, batch, reviewed_by, reviewed_at, batch_id):
        records = []
        pages = {page.id: page for page in self.queue.pages}
        chunks = {chunk.id: chunk for chunk in self.queue.chunks}
        for request in batch.items:
            target = pages[request.target_id] if request.target_type is ReviewTargetType.PAGE else chunks[request.target_id]
            history = [record for record in self.records if record.target_type is request.target_type and record.target_id == request.target_id]
            record = build_review_record(
                record_id=f"review-{len(self.records) + 1}",
                document_id=document_id,
                source_file_id=source_file_id,
                request=request,
                previous_status=target.review_status,
                revision=len(history) + 1,
                reviewed_by=reviewed_by,
                reviewed_at=reviewed_at,
                batch_id=batch_id,
            )
            if request.target_type is ReviewTargetType.PAGE:
                pages[request.target_id] = target.model_copy(update={"review_status": request.decision})
            else:
                chunks[request.target_id] = target.model_copy(update={"review_status": request.decision})
            self.records.append(record)
            records.append(record)
        self.queue = self.queue.model_copy(update={"pages": tuple(pages.values()), "chunks": tuple(chunks.values())})
        return records

    async def list_records(self, *, source_file_id, target_type=None, target_id=None):
        return [record for record in self.records if record.source_file_id == source_file_id and (target_type is None or record.target_type is target_type) and (target_id is None or record.target_id == target_id)]

    async def publication_gate(self, *, source_file_id, chunk_id):
        chunk = next(chunk for chunk in self.queue.chunks if chunk.id == chunk_id)
        pages = {page.id: page.review_status for page in self.queue.pages}
        return evaluate_publication_gate(
            chunk_status=chunk.review_status,
            page_statuses=tuple(pages[page_id] for page_id in chunk.cleaned_page_ids),
        )

    async def chunk_set_publication_gate(self, *, source_file_id, chunk_set_id):
        decisions = [await self.publication_gate(source_file_id=source_file_id, chunk_id=chunk.id) for chunk in self.queue.chunks]
        reasons = tuple(reason for decision in decisions for reason in decision.reasons)
        return PublicationGateDecision(allowed=not reasons, reasons=reasons)


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 10), "white").save(output, format="PNG")
    return output.getvalue()


def test_admin_reviews_page_and_chunk_then_finalizes_review_gate(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    ingestion = _InMemoryIngestionRepository()
    app = make_authed_test_app(user_factory=_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_ingestion_job_repository] = lambda: ingestion
    app.dependency_overrides[source_documents.get_optional_ingestion_job_repository] = lambda: ingestion
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        document = client.post(
            "/api/source-documents",
            json={
                "title": "复核测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "gazetteer",
                "source_level": "A",
                "holder": "测试资料组",
            },
        ).json()
        upload = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("scan.png", _png_bytes(), "image/png")},
        ).json()["items"][0]
        source_file = upload["file"]
        job_id = upload["ingestion_job"]["id"]
        job = ingestion.jobs[job_id]
        for step_name in (IngestionStepName.PARSE, IngestionStepName.OCR, IngestionStepName.CLEAN, IngestionStepName.CHUNK):
            job, _ = begin_step(job, step_name=step_name, worker_id="worker-1", now=datetime.now(UTC))
            job, _ = complete_step(job, step_name=step_name, output_ref=f"artifact:{step_name.value}", now=datetime.now(UTC))
        ingestion.jobs[job_id] = job
        reviews = _InMemoryReviewRepository(document_id=document["id"], source_file_id=source_file["id"])
        app.dependency_overrides[source_documents.get_review_repository] = lambda: reviews
        base = f"/api/source-documents/{document['id']}/files/{source_file['id']}/review"

        queue = client.get(f"{base}/queue", params={"chunk_set_id": "chunk-set-1"})
        blocked = client.post(
            f"{base}/finalize",
            json={"chunk_set_id": "chunk-set-1", "ingestion_job_id": job_id},
        )
        decisions = client.post(
            f"{base}/decisions",
            json={
                "items": [
                    {"target_type": "page", "target_id": "cleaned-page-1", "decision": "reviewed"},
                    {"target_type": "chunk", "target_id": "chunk-1", "decision": "reviewed", "comment": "页码一致"},
                ]
            },
        )
        history = client.get(f"{base}/history")
        finalized = client.post(
            f"{base}/finalize",
            json={"chunk_set_id": "chunk-set-1", "ingestion_job_id": job_id},
        )

    assert queue.status_code == 200
    assert queue.json()["pages"][0]["raw_text"] == "後臺"
    assert queue.json()["pages"][0]["clean_text"] == "后台"
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "review_gate_blocked"
    assert decisions.status_code == 200
    assert len(decisions.json()) == 2
    assert [record["revision"] for record in history.json()] == [1, 1]
    assert finalized.status_code == 200
    assert finalized.json()["current_step"] == "index"
    assert finalized.json()["progress_percent"] == 85


def test_non_admin_cannot_read_review_queue(tmp_path):
    app = make_authed_test_app(user_factory=lambda: _user("user"))
    app.dependency_overrides[source_documents.get_source_document_repository] = InMemorySourceDocumentRepository
    app.dependency_overrides[source_documents.get_source_file_repository] = InMemorySourceFileRepository
    app.dependency_overrides[source_documents.get_review_repository] = lambda: object()
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        response = client.get(
            "/api/source-documents/document-1/files/file-1/review/queue",
            params={"chunk_set_id": "chunk-set-1"},
        )

    assert response.status_code == 403
