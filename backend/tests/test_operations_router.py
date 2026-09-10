from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture.ingestion import begin_step, create_ingestion_job, fail_step

from app.gateway.auth.models import User
from app.gateway.routers import operations


def _user(role: str = "admin") -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email=f"{role}@example.com",
        password_hash="x",
        system_role=role,
    )


class _OperationsRepository:
    async def dashboard(self, *, days: int):
        assert days == 30
        return operations.build_dashboard_metrics(
            answer_events=[],
            feedback_ratings=[],
            unanswered_count=0,
            map_click_count=0,
            correction_count=0,
            hot_entities=[],
        )

    async def record_event(self, body, *, user_id: str):
        return {"id": "event-1", **body.model_dump(), "user_id": user_id, "occurred_at": "2026-07-29T00:00:00Z"}

    async def list_corrections(self, *, limit: int):
        return []

    async def create_correction(self, body, *, actor_id: str):
        return {"id": "correction-1", **body.model_dump(), "actor_id": actor_id, "created_at": "2026-07-29T00:00:00Z"}

    async def list_evaluation_cases(self):
        return []

    async def create_evaluation_case(self, body, *, actor_id: str):
        return {"id": "case-1", **body.model_dump(), "created_by": actor_id, "created_at": "2026-07-29T00:00:00Z"}

    async def create_evaluation_run(self, body, *, actor_id: str):
        return {"id": "eval-1", "release_id": body.release_id, "status": "completed", "total": 0, "passed": 0, "pass_rate": None, "created_by": actor_id, "created_at": "2026-07-29T00:00:00Z", "results": []}

    async def list_evaluation_runs(self, *, limit: int):
        return []

    async def list_asset_versions(self):
        return []


class _IngestionOperationsRepository:
    def __init__(self):
        now = datetime.now(UTC)
        job, event = create_ingestion_job(
            job_id="job-1",
            document_id="document-1",
            source_file_id="file-1",
            idempotency_key="upload:file-1",
            created_by="admin-id",
            now=now,
        )
        running, _ = begin_step(
            job,
            step_name=job.current_step,
            worker_id="worker-1",
            now=now,
        )
        failed, _ = fail_step(
            running,
            step_name=running.current_step,
            error_code="ocr_timeout",
            error_message="识别服务超时",
            retryable=True,
            now=now,
        )
        self.jobs = {failed.id: failed}

    async def list_recent(self, *, limit, statuses=None):
        values = list(self.jobs.values())
        if statuses:
            values = [job for job in values if job.status in statuses]
        return [(job, "吴县志", "scan.png") for job in values[:limit]]

    async def get(self, job_id):
        return self.jobs.get(job_id)

    async def get_with_context(self, job_id):
        job = self.jobs.get(job_id)
        return (job, "吴县志", "scan.png") if job is not None else None

    async def save(self, job, event, *, expected_version):
        assert job.version == expected_version + 1
        self.jobs[job.id] = job


def _app(role: str):
    app = make_authed_test_app(user_factory=lambda: _user(role))
    app.dependency_overrides[operations.get_operations_repository] = _OperationsRepository
    app.include_router(operations.router)
    return app


def _task_app(repository: _IngestionOperationsRepository):
    app = _app("admin")
    app.dependency_overrides[operations.get_ingestion_job_repository] = lambda: repository
    return app


def test_admin_can_open_dashboard_and_create_audit_records() -> None:
    with TestClient(_app("admin")) as client:
        dashboard = client.get("/api/operations/dashboard?days=30")
        correction = client.post(
            "/api/operations/corrections",
            json={"target_type": "map", "target_id": "pt-mudu", "summary": "校正坐标依据", "before": {"confidence": "approximate"}, "after": {"confidence": "exact"}},
        )

    assert dashboard.status_code == 200
    assert dashboard.json()["three_dimensional_load_success_rate"] is None
    assert correction.status_code == 201
    assert correction.json()["id"] == "correction-1"


def test_public_user_cannot_open_operations_dashboard() -> None:
    with TestClient(_app("user")) as client:
        response = client.get("/api/operations/dashboard")

    assert response.status_code == 403


def test_authenticated_user_can_record_map_click_but_not_answer_judgement() -> None:
    with TestClient(_app("user")) as client:
        click = client.post("/api/operations/events", json={"event_type": "map_point_click", "entity_id": "pt-mudu"})
        answer = client.post("/api/operations/events", json={"event_type": "answer_completed", "citation_count": 2})
        judgement = client.post("/api/operations/events", json={"event_type": "answer_completed", "is_accurate": True})

    assert click.status_code == 201
    assert answer.status_code == 201
    assert judgement.status_code == 403


def test_operations_task_center_lists_failed_step_and_retries_it() -> None:
    repository = _IngestionOperationsRepository()
    with TestClient(_task_app(repository)) as client:
        listed = client.get("/api/operations/tasks?status_filter=failed")
        retried = client.post("/api/operations/tasks/ingestion-job:job-1/retry", json={})

    assert listed.status_code == 200
    task = listed.json()[0]
    assert task["title"] == "吴县志"
    assert task["failure_step"] == "parse"
    assert task["failure_step_label"] == "文档解析"
    assert task["error_code"] == "ocr_timeout"
    assert task["retry_count"] == 0
    assert retried.status_code == 200
    assert retried.json()["status"] == "pending"
    assert retried.json()["title"] == "吴县志"
