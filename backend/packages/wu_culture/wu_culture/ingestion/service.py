from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IngestionStateError(ValueError):
    """Raised when a requested ingestion transition is illegal."""


class IngestionConcurrencyError(RuntimeError):
    """Raised when a persisted job changed before an optimistic update."""


class IngestionIdempotencyConflict(ValueError):
    """Raised when one idempotency key is reused for another source file."""


class IngestionJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionStepName(StrEnum):
    PARSE = "parse"
    OCR = "ocr"
    CLEAN = "clean"
    CHUNK = "chunk"
    REVIEW = "review"
    INDEX = "index"


class IngestionStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


INGESTION_STEP_ORDER = (
    IngestionStepName.PARSE,
    IngestionStepName.OCR,
    IngestionStepName.CLEAN,
    IngestionStepName.CHUNK,
    IngestionStepName.REVIEW,
    IngestionStepName.INDEX,
)

_STEP_PROGRESS = {
    IngestionStepName.PARSE: 15,
    IngestionStepName.OCR: 35,
    IngestionStepName.CLEAN: 55,
    IngestionStepName.CHUNK: 70,
    IngestionStepName.REVIEW: 85,
    IngestionStepName.INDEX: 100,
}


class _IngestionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IngestionStep(_IngestionModel):
    name: IngestionStepName
    status: IngestionStepStatus = IngestionStepStatus.PENDING
    attempt_count: int = Field(default=0, ge=0)
    worker_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_ref: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = True


class IngestionJob(_IngestionModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_file_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=255)
    created_by: str = Field(min_length=1)
    status: IngestionJobStatus
    current_step: IngestionStepName | None
    progress_percent: int = Field(ge=0, le=100)
    steps: tuple[IngestionStep, ...] = Field(min_length=len(INGESTION_STEP_ORDER), max_length=len(INGESTION_STEP_ORDER))
    error_code: str | None = None
    error_message: str | None = None
    owner_worker_id: str | None = None
    lease_expires_at: datetime | None = None
    version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_steps(self) -> IngestionJob:
        if tuple(step.name for step in self.steps) != INGESTION_STEP_ORDER:
            raise ValueError("ingestion steps must use the canonical order exactly once")
        return self

    def step(self, name: IngestionStepName) -> IngestionStep:
        return self.steps[INGESTION_STEP_ORDER.index(name)]


class IngestionEvent(_IngestionModel):
    job_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1)
    job_status: IngestionJobStatus
    step_name: IngestionStepName | None = None
    step_status: IngestionStepStatus | None = None
    progress_percent: int = Field(ge=0, le=100)
    error_code: str | None = None
    error_message: str | None = None
    actor_id: str = Field(min_length=1)
    created_at: datetime


class IngestionJobRepository(Protocol):
    async def create(self, job: IngestionJob, event: IngestionEvent) -> tuple[IngestionJob, bool]: ...

    async def get(self, job_id: str) -> IngestionJob | None: ...

    async def get_with_context(
        self,
        job_id: str,
    ) -> tuple[IngestionJob, str | None, str | None] | None: ...

    async def list_for_source_file(self, source_file_id: str) -> list[IngestionJob]: ...

    async def list_recent(
        self,
        *,
        limit: int = 100,
        statuses: set[IngestionJobStatus] | None = None,
    ) -> list[tuple[IngestionJob, str | None, str | None]]: ...

    async def list_events(self, job_id: str, *, after_sequence: int = 0) -> list[IngestionEvent]: ...

    async def save(self, job: IngestionJob, event: IngestionEvent, *, expected_version: int) -> None: ...

    async def try_start_step(
        self,
        job_id: str,
        *,
        step_name: IngestionStepName,
        worker_id: str,
        max_concurrent_jobs: int,
        lease_seconds: int,
        now: datetime,
    ) -> IngestionJob | None: ...

    async def renew_lease(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: int,
        now: datetime,
    ) -> IngestionJob | None: ...

    async def recover_interrupted(self, *, now: datetime, grace_seconds: int = 0) -> list[IngestionJob]: ...


def create_ingestion_job(
    *,
    job_id: str,
    document_id: str,
    source_file_id: str,
    idempotency_key: str,
    created_by: str,
    now: datetime,
) -> tuple[IngestionJob, IngestionEvent]:
    _require_timezone(now)
    job = IngestionJob(
        id=job_id,
        document_id=document_id,
        source_file_id=source_file_id,
        idempotency_key=idempotency_key,
        created_by=created_by,
        status=IngestionJobStatus.PENDING,
        current_step=IngestionStepName.PARSE,
        progress_percent=0,
        steps=tuple(IngestionStep(name=name) for name in INGESTION_STEP_ORDER),
        version=1,
        event_sequence=1,
        created_at=now,
        updated_at=now,
    )
    return job, _event(job, event_type="job_created", actor_id=created_by, now=now)


def begin_step(
    job: IngestionJob,
    *,
    step_name: IngestionStepName,
    worker_id: str,
    lease_expires_at: datetime | None = None,
    now: datetime,
) -> tuple[IngestionJob, IngestionEvent]:
    _require_timezone(now)
    if job.status is IngestionJobStatus.CANCELLED:
        raise IngestionStateError("cancelled ingestion job cannot start a step")
    if job.status in {IngestionJobStatus.COMPLETED, IngestionJobStatus.FAILED}:
        raise IngestionStateError(f"{job.status.value} ingestion job cannot start a step")
    if job.current_step is not step_name:
        expected = job.current_step.value if job.current_step else "none"
        raise IngestionStateError(f"expected step {expected}, not {step_name.value}")
    step = job.step(step_name)
    if step.status is not IngestionStepStatus.PENDING:
        raise IngestionStateError(f"step {step_name.value} is {step.status.value}, not pending")
    if lease_expires_at is not None:
        _require_timezone(lease_expires_at)
        if lease_expires_at <= now:
            raise ValueError("ingestion lease must expire after step start")
    updated_step = step.model_copy(
        update={
            "status": IngestionStepStatus.RUNNING,
            "attempt_count": step.attempt_count + 1,
            "worker_id": worker_id,
            "started_at": now,
            "finished_at": None,
            "error_code": None,
            "error_message": None,
        }
    )
    updated = _update_job(
        job,
        step=updated_step,
        now=now,
        status=IngestionJobStatus.RUNNING,
        error_code=None,
        error_message=None,
        owner_worker_id=worker_id,
        lease_expires_at=lease_expires_at,
    )
    return updated, _event(updated, event_type="step_started", actor_id=worker_id, now=now, step=updated_step)


def complete_step(
    job: IngestionJob,
    *,
    step_name: IngestionStepName,
    output_ref: str | None,
    now: datetime,
) -> tuple[IngestionJob, IngestionEvent]:
    _require_timezone(now)
    step = _require_running_step(job, step_name)
    updated_step = step.model_copy(
        update={
            "status": IngestionStepStatus.COMPLETED,
            "finished_at": now,
            "output_ref": output_ref,
            "error_code": None,
            "error_message": None,
        }
    )
    index = INGESTION_STEP_ORDER.index(step_name)
    if step_name is IngestionStepName.INDEX:
        status = IngestionJobStatus.COMPLETED
        current_step = None
        completed_at = now
    else:
        current_step = INGESTION_STEP_ORDER[index + 1]
        status = IngestionJobStatus.AWAITING_REVIEW if current_step is IngestionStepName.REVIEW else IngestionJobStatus.PENDING
        completed_at = None
    updated = _update_job(
        job,
        step=updated_step,
        now=now,
        status=status,
        current_step=current_step,
        progress_percent=_STEP_PROGRESS[step_name],
        completed_at=completed_at,
        error_code=None,
        error_message=None,
        owner_worker_id=None,
        lease_expires_at=None,
    )
    return updated, _event(updated, event_type="step_completed", actor_id=step.worker_id or job.created_by, now=now, step=updated_step)


def fail_step(
    job: IngestionJob,
    *,
    step_name: IngestionStepName,
    error_code: str,
    error_message: str,
    retryable: bool,
    now: datetime,
) -> tuple[IngestionJob, IngestionEvent]:
    _require_timezone(now)
    step = _require_running_step(job, step_name)
    updated_step = step.model_copy(
        update={
            "status": IngestionStepStatus.FAILED,
            "finished_at": now,
            "error_code": error_code,
            "error_message": error_message,
            "retryable": retryable,
        }
    )
    updated = _update_job(
        job,
        step=updated_step,
        now=now,
        status=IngestionJobStatus.FAILED,
        error_code=error_code,
        error_message=error_message,
        owner_worker_id=None,
        lease_expires_at=None,
    )
    return updated, _event(
        updated,
        event_type="step_failed",
        actor_id=step.worker_id or job.created_by,
        now=now,
        step=updated_step,
        error_code=error_code,
        error_message=error_message,
    )


def retry_failed_step(
    job: IngestionJob,
    *,
    step_name: IngestionStepName,
    now: datetime,
    requested_by: str | None = None,
) -> tuple[IngestionJob, IngestionEvent]:
    _require_timezone(now)
    if job.status is not IngestionJobStatus.FAILED or job.current_step is not step_name:
        raise IngestionStateError("only the current failed step can be retried")
    step = job.step(step_name)
    if step.status is not IngestionStepStatus.FAILED:
        raise IngestionStateError(f"step {step_name.value} is not failed")
    if not step.retryable:
        raise IngestionStateError(f"step {step_name.value} is not retryable")
    updated_step = step.model_copy(
        update={
            "status": IngestionStepStatus.PENDING,
            "worker_id": None,
            "started_at": None,
            "finished_at": None,
            "error_code": None,
            "error_message": None,
        }
    )
    updated = _update_job(
        job,
        step=updated_step,
        now=now,
        status=IngestionJobStatus.PENDING,
        error_code=None,
        error_message=None,
        owner_worker_id=None,
        lease_expires_at=None,
    )
    actor_id = requested_by or job.created_by
    return updated, _event(updated, event_type="step_retry_requested", actor_id=actor_id, now=now, step=updated_step)


def cancel_job(
    job: IngestionJob,
    *,
    requested_by: str,
    now: datetime,
) -> tuple[IngestionJob, IngestionEvent | None]:
    _require_timezone(now)
    if job.status is IngestionJobStatus.CANCELLED:
        return job, None
    if job.status is IngestionJobStatus.COMPLETED:
        raise IngestionStateError("completed ingestion job cannot be cancelled")
    step = job.step(job.current_step) if job.current_step is not None else None
    updated_step = None
    if step is not None and step.status is IngestionStepStatus.RUNNING:
        updated_step = step.model_copy(update={"status": IngestionStepStatus.CANCELLED, "finished_at": now})
    updated = _update_job(
        job,
        step=updated_step,
        now=now,
        status=IngestionJobStatus.CANCELLED,
        completed_at=now,
        owner_worker_id=None,
        lease_expires_at=None,
    )
    return updated, _event(updated, event_type="job_cancelled", actor_id=requested_by, now=now, step=updated_step or step)


def recover_interrupted_job(
    job: IngestionJob,
    *,
    now: datetime,
    worker_id: str = "gateway-recovery",
) -> tuple[IngestionJob, IngestionEvent]:
    """Return an interrupted running step to pending after process restart."""

    _require_timezone(now)
    if job.status is not IngestionJobStatus.RUNNING or job.current_step is None:
        raise IngestionStateError("only a running ingestion job can be recovered")
    if job.lease_expires_at is not None and job.lease_expires_at > now:
        raise IngestionStateError("ingestion job lease is still valid")
    step = job.step(job.current_step)
    if step.status is not IngestionStepStatus.RUNNING:
        raise IngestionStateError("running ingestion job has no running current step")
    updated_step = step.model_copy(
        update={
            "status": IngestionStepStatus.PENDING,
            "worker_id": None,
            "started_at": None,
            "finished_at": None,
            "error_code": None,
            "error_message": None,
        }
    )
    updated = _update_job(
        job,
        step=updated_step,
        now=now,
        status=IngestionJobStatus.PENDING,
        error_code=None,
        error_message=None,
        owner_worker_id=None,
        lease_expires_at=None,
    )
    return updated, _event(updated, event_type="job_recovered", actor_id=worker_id, now=now, step=updated_step)


def _require_running_step(job: IngestionJob, step_name: IngestionStepName) -> IngestionStep:
    if job.status is IngestionJobStatus.CANCELLED:
        raise IngestionStateError("cancelled ingestion job cannot transition")
    if job.current_step is not step_name:
        expected = job.current_step.value if job.current_step else "none"
        raise IngestionStateError(f"expected step {expected}, not {step_name.value}")
    step = job.step(step_name)
    if step.status is not IngestionStepStatus.RUNNING:
        raise IngestionStateError(f"step {step_name.value} is {step.status.value}, not running")
    return step


_UNSET = object()


def _update_job(
    job: IngestionJob,
    *,
    step: IngestionStep | None,
    now: datetime,
    status: IngestionJobStatus,
    current_step: IngestionStepName | None | object = _UNSET,
    progress_percent: int | object = _UNSET,
    error_code: str | None | object = _UNSET,
    error_message: str | None | object = _UNSET,
    completed_at: datetime | None | object = _UNSET,
    owner_worker_id: str | None | object = _UNSET,
    lease_expires_at: datetime | None | object = _UNSET,
) -> IngestionJob:
    steps = list(job.steps)
    if step is not None:
        steps[INGESTION_STEP_ORDER.index(step.name)] = step
    updates: dict[str, object] = {
        "steps": tuple(steps),
        "status": status,
        "version": job.version + 1,
        "event_sequence": job.event_sequence + 1,
        "updated_at": now,
    }
    for name, value in (
        ("current_step", current_step),
        ("progress_percent", progress_percent),
        ("error_code", error_code),
        ("error_message", error_message),
        ("completed_at", completed_at),
        ("owner_worker_id", owner_worker_id),
        ("lease_expires_at", lease_expires_at),
    ):
        if value is not _UNSET:
            updates[name] = value
    return job.model_copy(update=updates)


def _event(
    job: IngestionJob,
    *,
    event_type: str,
    actor_id: str,
    now: datetime,
    step: IngestionStep | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> IngestionEvent:
    return IngestionEvent(
        job_id=job.id,
        sequence=job.event_sequence,
        event_type=event_type,
        job_status=job.status,
        step_name=step.name if step else None,
        step_status=step.status if step else None,
        progress_percent=job.progress_percent,
        error_code=error_code,
        error_message=error_message,
        actor_id=actor_id,
        created_at=now,
    )


def _require_timezone(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("ingestion timestamps must include a timezone")
