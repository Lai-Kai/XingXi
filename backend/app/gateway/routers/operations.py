from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from wu_culture.ingestion import (
    IngestionConcurrencyError,
    IngestionJob,
    IngestionJobRepository,
    IngestionJobStatus,
    IngestionStateError,
    IngestionStepStatus,
    retry_failed_step,
)

from app.gateway.deps import require_business_capability
from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.operations import OperationsRepository

router = APIRouter(prefix="/api/operations", tags=["operations"])


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HotEntity(_Model):
    entity_id: str
    name: str
    views: int


class OperationsDashboard(_Model):
    answer_accuracy_rate: float | None
    citation_rate: float | None
    refusal_compliance_rate: float | None
    user_satisfaction_rate: float | None
    answer_count: int
    unanswered_count: int
    map_point_click_count: int
    manual_correction_count: int
    three_dimensional_load_success_rate: None = None
    hot_entities: tuple[HotEntity, ...]


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def build_dashboard_metrics(
    *, answer_events: list[dict[str, Any]], feedback_ratings: list[int], unanswered_count: int, map_click_count: int, correction_count: int, hot_entities: list[tuple[str, str, int]], evaluation_outcomes: list[bool] | None = None
) -> OperationsDashboard:
    judged = [bool(row["is_accurate"]) for row in answer_events if row.get("is_accurate") is not None]
    # Offline regression observations are not online answer-accuracy judgements.
    refusals = [row for row in answer_events if row.get("refused")]
    return OperationsDashboard(
        answer_accuracy_rate=_rate(sum(judged), len(judged)),
        citation_rate=_rate(sum((row.get("citation_count") or 0) > 0 for row in answer_events), len(answer_events)),
        refusal_compliance_rate=_rate(sum(row.get("refusal_compliant") is True for row in refusals), len(refusals)),
        user_satisfaction_rate=_rate(sum(rating > 0 for rating in feedback_ratings), len(feedback_ratings)),
        answer_count=len(answer_events),
        unanswered_count=unanswered_count,
        map_point_click_count=map_click_count,
        manual_correction_count=correction_count,
        hot_entities=tuple(HotEntity(entity_id=item[0], name=item[1], views=item[2]) for item in hot_entities),
    )


class EvaluationResult(_Model):
    case_id: str
    actual_status: Literal["answered", "refused"]
    citation_count: int = Field(ge=0)
    answer: str
    passed: bool
    failure_reasons: tuple[str, ...]


class RegressionReport(_Model):
    total: int
    passed: int
    pass_rate: float | None
    results: tuple[EvaluationResult, ...]


def grade_regression_run(*, cases: list[dict[str, Any]], observations: list[dict[str, Any]]) -> RegressionReport:
    from deerflow.persistence.operations.grading import grade_manual_regression

    return RegressionReport.model_validate(grade_manual_regression(cases=cases, observations=observations))


class OperationEventCreate(_Model):
    event_type: Literal["answer_completed", "citation_open", "search_miss", "map_point_click", "entity_view"]
    event_key: str | None = Field(default=None, max_length=255)
    thread_id: str | None = None
    run_id: str | None = None
    release_id: str | None = None
    entity_id: str | None = None
    entity_name: str | None = None
    citation_count: int | None = Field(default=None, ge=0)
    is_accurate: bool | None = None
    refused: bool | None = None
    refusal_compliant: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationEvent(OperationEventCreate):
    id: str
    user_id: str
    occurred_at: datetime


class CorrectionCreate(_Model):
    target_type: Literal["source", "knowledge", "entity", "graph", "map"]
    target_id: str = Field(min_length=1, max_length=255)
    release_id: str | None = None
    summary: str = Field(min_length=1, max_length=4000)
    before: dict[str, Any]
    after: dict[str, Any]


class Correction(CorrectionCreate):
    id: str
    actor_id: str
    created_at: datetime


class EvaluationCaseCreate(_Model):
    name: str = Field(min_length=1, max_length=255)
    question: str = Field(min_length=1, max_length=4000)
    expected_status: Literal["answered", "refused"]
    min_citations: int = Field(default=0, ge=0, le=100)
    required_terms: tuple[str, ...] = ()
    active: bool = True


class EvaluationCase(EvaluationCaseCreate):
    id: str
    created_by: str
    created_at: datetime


class EvaluationObservation(_Model):
    case_id: str
    actual_status: Literal["answered", "refused"]
    citation_count: int = Field(ge=0)
    answer: str = ""


class EvaluationRunCreate(_Model):
    release_id: str | None = None
    asset_version_id: str | None = None
    case_ids: tuple[str, ...] = ()
    observations: tuple[EvaluationObservation, ...]


class EvaluationRun(_Model):
    id: str
    release_id: str | None
    asset_version_id: str | None = None
    status: Literal["completed"]
    total: int
    passed: int
    pass_rate: float | None
    created_by: str
    created_at: datetime
    results: tuple[EvaluationResult, ...]


class AssetVersion(_Model):
    id: str
    knowledge_release_id: str
    knowledge_release_version: str
    graph_manifest_sha256: str
    map_manifest_sha256: str
    entity_count: int
    map_point_count: int
    created_by: str
    created_at: datetime


class OperationTaskStep(_Model):
    name: str
    label: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    attempt_count: int = Field(ge=0)
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool


class OperationTask(_Model):
    id: str
    kind: Literal["ingestion"]
    title: str
    document_id: str
    source_file_id: str
    filename: str | None
    status: IngestionJobStatus
    current_step: str | None
    current_step_label: str | None
    progress_percent: int = Field(ge=0, le=100)
    attempt_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    failure_step: str | None = None
    failure_step_label: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool
    steps: tuple[OperationTaskStep, ...]
    created_at: datetime
    updated_at: datetime


_INGESTION_STEP_LABELS = {
    "parse": "文档解析",
    "ocr": "扫描识别",
    "clean": "文本清洗",
    "chunk": "结构化切分",
    "review": "人工复核",
    "index": "知识索引",
}


def _operation_task_from_job(
    job: IngestionJob,
    *,
    document_title: str | None = None,
    filename: str | None = None,
) -> OperationTask:
    failed_step = next((step for step in job.steps if step.status is IngestionStepStatus.FAILED), None)
    current_step = job.current_step.value if job.current_step else None
    attempt_count = failed_step.attempt_count if failed_step is not None else sum(step.attempt_count for step in job.steps)
    return OperationTask(
        id=f"ingestion-job:{job.id}",
        kind="ingestion",
        title=document_title or filename or "未命名资料",
        document_id=job.document_id,
        source_file_id=job.source_file_id,
        filename=filename,
        status=job.status,
        current_step=current_step,
        current_step_label=_INGESTION_STEP_LABELS.get(current_step) if current_step else None,
        progress_percent=job.progress_percent,
        attempt_count=attempt_count,
        retry_count=max(0, attempt_count - 1),
        failure_step=failed_step.name.value if failed_step else None,
        failure_step_label=_INGESTION_STEP_LABELS.get(failed_step.name.value) if failed_step else None,
        error_code=failed_step.error_code if failed_step else job.error_code,
        error_message=failed_step.error_message if failed_step else job.error_message,
        retryable=bool(failed_step and failed_step.retryable),
        steps=tuple(
            OperationTaskStep(
                name=step.name.value,
                label=_INGESTION_STEP_LABELS[step.name.value],
                status=step.status,
                attempt_count=step.attempt_count,
                error_code=step.error_code,
                error_message=step.error_message,
                retryable=step.retryable,
            )
            for step in job.steps
        ),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def get_operations_repository() -> OperationsRepository:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Operations require a SQL database")
    return OperationsRepository(sf)


def get_ingestion_job_repository() -> IngestionJobRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Task recovery requires a SQL database")
    from deerflow.persistence.wu_culture import SqlIngestionJobRepository

    return SqlIngestionJobRepository(session_factory)


async def _operator_id(request: Request) -> str:
    user = await require_business_capability(request, "governance:read", detail="Governance privileges are required")
    return str(user.id)


async def _source_manager_id(request: Request) -> str:
    user = await require_business_capability(request, "source:manage", detail="Source management privileges are required")
    return str(user.id)


@router.get("/tasks", response_model=list[OperationTask])
async def list_operation_tasks(
    request: Request,
    status_filter: Literal["all", "pending", "running", "awaiting_review", "completed", "failed", "cancelled"] = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=500),
    repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> list[OperationTask]:
    await _operator_id(request)
    statuses = None if status_filter == "all" else {IngestionJobStatus(status_filter)}
    rows = await repository.list_recent(limit=limit, statuses=statuses)
    return [_operation_task_from_job(job, document_title=document_title, filename=filename) for job, document_title, filename in rows]


@router.post("/tasks/{task_id}/retry", response_model=OperationTask)
async def retry_operation_task(
    task_id: str,
    request: Request,
    repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> OperationTask:
    actor_id = await _source_manager_id(request)
    prefix = "ingestion-job:"
    if not task_id.startswith(prefix):
        raise HTTPException(status_code=404, detail={"code": "operation_task_not_found", "message": "This task type cannot be recovered here"})
    job_id = task_id.removeprefix(prefix)
    job = await repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "operation_task_not_found", "message": "The operation task was not found"})
    if job.current_step is None:
        raise HTTPException(status_code=409, detail={"code": "operation_task_not_retryable", "message": "The task has no failed step to retry"})
    try:
        updated, event = retry_failed_step(job, step_name=job.current_step, requested_by=actor_id, now=datetime.now(UTC))
        await repository.save(updated, event, expected_version=job.version)
    except (IngestionStateError, IngestionConcurrencyError) as exc:
        raise HTTPException(status_code=409, detail={"code": "operation_task_retry_conflict", "message": str(exc)}) from exc
    context = await repository.get_with_context(updated.id)
    if context is None:
        return _operation_task_from_job(updated)
    refreshed, document_title, filename = context
    return _operation_task_from_job(refreshed, document_title=document_title, filename=filename)


@router.get("/dashboard", response_model=OperationsDashboard)
async def dashboard(request: Request, days: int = Query(default=30, ge=1, le=365), repository: OperationsRepository = Depends(get_operations_repository)) -> OperationsDashboard:
    await _operator_id(request)
    return await repository.dashboard(days=days)


@router.post("/events", response_model=OperationEvent, status_code=status.HTTP_201_CREATED)
async def record_event(body: OperationEventCreate, request: Request, repository: OperationsRepository = Depends(get_operations_repository)):
    user = await require_business_capability(request, "knowledge:read", detail="Authentication is required")
    if body.event_type == "answer_completed" and getattr(user, "system_role", "user") != "admin" and (body.is_accurate is not None or body.refusal_compliant is not None):
        raise HTTPException(status_code=403, detail="Only trusted operators can record answer judgements")
    return await repository.record_event(body, user_id=str(user.id))


@router.get("/corrections", response_model=list[Correction])
async def list_corrections(request: Request, limit: int = Query(default=50, ge=1, le=200), repository: OperationsRepository = Depends(get_operations_repository)):
    await _operator_id(request)
    return await repository.list_corrections(limit=limit)


@router.post("/corrections", response_model=Correction, status_code=status.HTTP_201_CREATED)
async def create_correction(body: CorrectionCreate, request: Request, repository: OperationsRepository = Depends(get_operations_repository)):
    return await repository.create_correction(body, actor_id=await _operator_id(request))


@router.get("/evaluations/cases", response_model=list[EvaluationCase])
async def list_evaluation_cases(request: Request, repository: OperationsRepository = Depends(get_operations_repository)):
    await _operator_id(request)
    return await repository.list_evaluation_cases()


@router.post("/evaluations/cases", response_model=EvaluationCase, status_code=status.HTTP_201_CREATED)
async def create_evaluation_case(body: EvaluationCaseCreate, request: Request, repository: OperationsRepository = Depends(get_operations_repository)):
    return await repository.create_evaluation_case(body, actor_id=await _operator_id(request))


@router.get("/evaluations/runs", response_model=list[EvaluationRun])
async def list_evaluation_runs(request: Request, limit: int = Query(default=20, ge=1, le=100), repository: OperationsRepository = Depends(get_operations_repository)):
    await _operator_id(request)
    return await repository.list_evaluation_runs(limit=limit)


@router.post("/evaluations/runs", response_model=EvaluationRun, status_code=status.HTTP_201_CREATED)
async def create_evaluation_run(body: EvaluationRunCreate, request: Request, repository: OperationsRepository = Depends(get_operations_repository)):
    actor_id = await _operator_id(request)
    try:
        return await repository.create_evaluation_run(body, actor_id=actor_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/asset-versions", response_model=list[AssetVersion])
async def list_asset_versions(request: Request, repository: OperationsRepository = Depends(get_operations_repository)):
    await _operator_id(request)
    return await repository.list_asset_versions()


@router.post("/asset-versions/reconcile", response_model=list[AssetVersion])
async def reconcile_asset_versions(request: Request, repository: OperationsRepository = Depends(get_operations_repository)):
    actor_id = await _operator_id(request)
    from app.gateway.routers.knowledge_releases import get_knowledge_release_repository
    from app.gateway.routers.map_points import build_release_map_manifest

    releases = await get_knowledge_release_repository().list_releases()
    for release in releases:
        manifest = await build_release_map_manifest(release)
        await repository.ensure_asset_snapshot(
            release_id=release.id,
            release_version=release.version,
            map_manifest=manifest,
            actor_id=actor_id,
        )
    return await repository.list_asset_versions()
