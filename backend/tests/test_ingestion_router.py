from __future__ import annotations

from io import BytesIO
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from PIL import Image
from wu_culture.ingestion import IngestionJobStatus, begin_step
from wu_culture.repositories import InMemorySourceDocumentRepository, InMemorySourceFileRepository

from app.gateway.auth.models import User
from app.gateway.routers import source_documents
from deerflow.object_storage import LocalObjectStorage


def _admin_user() -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email="admin@example.com",
        password_hash="x",
        system_role="admin",
    )


class _InMemoryIngestionRepository:
    def __init__(self):
        self.jobs = {}
        self.events = {}

    async def create(self, job, event):
        existing = next(
            (value for value in self.jobs.values() if value.created_by == job.created_by and value.idempotency_key == job.idempotency_key),
            None,
        )
        if existing is not None:
            return existing, False
        self.jobs[job.id] = job
        self.events[job.id] = [event]
        return job, True

    async def get(self, job_id):
        return self.jobs.get(job_id)

    async def list_for_source_file(self, source_file_id):
        return [job for job in self.jobs.values() if job.source_file_id == source_file_id]

    async def list_events(self, job_id, *, after_sequence=0):
        return [event for event in self.events.get(job_id, []) if event.sequence > after_sequence]

    async def save(self, job, event, *, expected_version):
        existing = self.jobs[job.id]
        assert existing.version == expected_version
        self.jobs[job.id] = job
        self.events[job.id].append(event)

    async def try_start_step(self, job_id, *, step_name, worker_id, max_concurrent_jobs, lease_seconds, now):
        if sum(job.status is IngestionJobStatus.RUNNING for job in self.jobs.values()) >= max_concurrent_jobs:
            return None
        current = self.jobs[job_id]
        started, event = begin_step(current, step_name=step_name, worker_id=worker_id, now=now)
        await self.save(started, event, expected_version=current.version)
        return started

    async def renew_lease(self, job_id, *, worker_id, lease_seconds, now):
        return self.jobs.get(job_id)

    async def recover_interrupted(self, *, now, grace_seconds=0):
        return []


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 10), "white").save(output, format="PNG")
    return output.getvalue()


def test_admin_controls_idempotent_ingestion_job_progress_retry_and_cancel(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    ingestion_repository = _InMemoryIngestionRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_ingestion_job_repository] = lambda: ingestion_repository
    app.dependency_overrides[source_documents.get_optional_ingestion_job_repository] = lambda: ingestion_repository
    app.dependency_overrides[source_documents.get_ingestion_max_concurrent_jobs] = lambda: 1
    app.dependency_overrides[source_documents.get_ingestion_lease_seconds] = lambda: 60
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        document = client.post(
            "/api/source-documents",
            json={
                "title": "入库任务测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "gazetteer",
                "source_level": "A",
                "holder": "测试资料组",
            },
        ).json()
        upload_item = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("scan.png", _png_bytes(), "image/png")},
        ).json()["items"][0]
        source_file = upload_item["file"]
        base = f"/api/source-documents/{document['id']}/files/{source_file['id']}/ingestion-jobs"
        created = client.post(base, json={"idempotency_key": "upload:scan:v1"})
        reused = client.post(base, json={"idempotency_key": "upload:scan:v1"})
        job_id = created.json()["job"]["id"]

        started_parse = client.post(f"{base}/{job_id}/steps/parse/start", json={"worker_id": "worker-1"})
        renewed_lease = client.post(f"{base}/{job_id}/lease", json={"worker_id": "worker-1"})
        completed_parse = client.post(f"{base}/{job_id}/steps/parse/complete", json={"output_ref": "parsed:1"})
        illegal_jump = client.post(f"{base}/{job_id}/steps/clean/start", json={"worker_id": "worker-1"})
        client.post(f"{base}/{job_id}/steps/ocr/start", json={"worker_id": "worker-1"})
        failed = client.post(
            f"{base}/{job_id}/steps/ocr/fail",
            json={"error_code": "ocr_timeout", "error_message": "provider timed out", "retryable": True},
        )
        retried = client.post(f"{base}/{job_id}/steps/ocr/retry")
        cancelled = client.post(f"{base}/{job_id}/cancel")
        cancelled_again = client.post(f"{base}/{job_id}/cancel")
        events = client.get(f"{base}/{job_id}/events", params={"after_sequence": 2})
        listed = client.get(base)

    assert upload_item["ingestion_job"]["status"] == "pending"
    assert upload_item["ingestion_error"] is None
    assert created.status_code == 201
    assert created.json()["reused_existing"] is False
    assert reused.json()["reused_existing"] is True
    assert reused.json()["job"]["id"] == job_id
    assert started_parse.json()["status"] == "running"
    assert renewed_lease.status_code == 200
    assert completed_parse.json()["current_step"] == "ocr"
    assert illegal_jump.status_code == 409
    assert illegal_jump.json()["detail"]["code"] == "invalid_ingestion_transition"
    assert failed.json()["status"] == "failed"
    assert failed.json()["error_code"] == "ocr_timeout"
    assert retried.json()["status"] == "pending"
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled_again.json() == cancelled.json()
    assert [event["event_type"] for event in events.json()] == [
        "step_completed",
        "step_started",
        "step_failed",
        "step_retry_requested",
        "job_cancelled",
    ]
    assert job_id in {job["id"] for job in listed.json()}
