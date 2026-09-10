from datetime import UTC, datetime, timedelta

import pytest
from wu_culture.ingestion import (
    IngestionJobStatus,
    IngestionStateError,
    IngestionStepName,
    IngestionStepStatus,
    begin_step,
    cancel_job,
    complete_step,
    create_ingestion_job,
    fail_step,
    recover_interrupted_job,
    retry_failed_step,
)

NOW = datetime(2026, 7, 21, 9, 0, tzinfo=UTC)


def _job():
    return create_ingestion_job(
        job_id="job-1",
        document_id="document-1",
        source_file_id="file-1",
        idempotency_key="upload:file-1:v1",
        created_by="admin-1",
        now=NOW,
    )


def test_normal_flow_stops_at_review_gate_before_indexing():
    job, event = _job()
    assert job.status is IngestionJobStatus.PENDING
    assert job.progress_percent == 0
    assert event.sequence == 1

    for step_name in (
        IngestionStepName.PARSE,
        IngestionStepName.OCR,
        IngestionStepName.CLEAN,
        IngestionStepName.CHUNK,
    ):
        job, started = begin_step(job, step_name=step_name, worker_id="worker-1", now=NOW)
        assert started.step_status is IngestionStepStatus.RUNNING
        job, completed = complete_step(job, step_name=step_name, output_ref=f"artifact:{step_name.value}", now=NOW)
        assert completed.step_status is IngestionStepStatus.COMPLETED

    assert job.status is IngestionJobStatus.AWAITING_REVIEW
    assert job.current_step is IngestionStepName.REVIEW
    assert job.step(IngestionStepName.REVIEW).status is IngestionStepStatus.PENDING
    assert job.step(IngestionStepName.INDEX).status is IngestionStepStatus.PENDING
    assert job.progress_percent == 70


def test_illegal_step_jump_is_rejected():
    job, _ = _job()

    with pytest.raises(IngestionStateError, match="expected step parse"):
        begin_step(job, step_name=IngestionStepName.CLEAN, worker_id="worker-1", now=NOW)


def test_failure_preserves_completed_steps_and_retry_resets_only_failed_step():
    job, _ = _job()
    job, _ = begin_step(job, step_name=IngestionStepName.PARSE, worker_id="worker-1", now=NOW)
    job, _ = complete_step(job, step_name=IngestionStepName.PARSE, output_ref="parsed:1", now=NOW)
    job, _ = begin_step(job, step_name=IngestionStepName.OCR, worker_id="worker-1", now=NOW)
    job, failed = fail_step(job, step_name=IngestionStepName.OCR, error_code="ocr_timeout", error_message="provider timed out", retryable=True, now=NOW)

    assert job.status is IngestionJobStatus.FAILED
    assert failed.error_code == "ocr_timeout"
    assert job.step(IngestionStepName.PARSE).output_ref == "parsed:1"
    assert job.step(IngestionStepName.PARSE).status is IngestionStepStatus.COMPLETED

    job, retried = retry_failed_step(job, step_name=IngestionStepName.OCR, now=NOW)
    assert job.status is IngestionJobStatus.PENDING
    assert job.current_step is IngestionStepName.OCR
    assert job.step(IngestionStepName.OCR).status is IngestionStepStatus.PENDING
    assert job.step(IngestionStepName.OCR).attempt_count == 1
    assert retried.event_type == "step_retry_requested"


def test_non_retryable_failure_cannot_be_retried():
    job, _ = _job()
    job, _ = begin_step(job, step_name=IngestionStepName.PARSE, worker_id="worker-1", now=NOW)
    job, _ = fail_step(job, step_name=IngestionStepName.PARSE, error_code="unsupported_type", error_message="unsupported", retryable=False, now=NOW)

    with pytest.raises(IngestionStateError, match="not retryable"):
        retry_failed_step(job, step_name=IngestionStepName.PARSE, now=NOW)


def test_cancel_is_terminal_and_idempotent():
    job, _ = _job()
    job, _ = begin_step(job, step_name=IngestionStepName.PARSE, worker_id="worker-1", now=NOW)
    cancelled, first_event = cancel_job(job, requested_by="admin-1", now=NOW)
    repeated, second_event = cancel_job(cancelled, requested_by="admin-1", now=NOW)

    assert cancelled.status is IngestionJobStatus.CANCELLED
    assert cancelled.step(IngestionStepName.PARSE).status is IngestionStepStatus.CANCELLED
    assert first_event.event_type == "job_cancelled"
    assert repeated == cancelled
    assert second_event is None

    with pytest.raises(IngestionStateError, match="cancelled"):
        begin_step(cancelled, step_name=IngestionStepName.PARSE, worker_id="worker-1", now=NOW)


def test_restart_recovery_requeues_running_step_without_losing_attempt_history():
    job, _ = _job()
    job, _ = begin_step(job, step_name=IngestionStepName.PARSE, worker_id="worker-before-restart", now=NOW)

    recovered, event = recover_interrupted_job(job, now=NOW, worker_id="gateway-recovery")

    assert recovered.status is IngestionJobStatus.PENDING
    assert recovered.current_step is IngestionStepName.PARSE
    assert recovered.step(IngestionStepName.PARSE).status is IngestionStepStatus.PENDING
    assert recovered.step(IngestionStepName.PARSE).attempt_count == 1
    assert recovered.step(IngestionStepName.PARSE).worker_id is None
    assert event.event_type == "job_recovered"


def test_restart_recovery_does_not_take_over_a_live_worker_lease():
    job, _ = _job()
    job, _ = begin_step(
        job,
        step_name=IngestionStepName.PARSE,
        worker_id="worker-live",
        lease_expires_at=NOW + timedelta(seconds=60),
        now=NOW,
    )

    with pytest.raises(IngestionStateError, match="lease is still valid"):
        recover_interrupted_job(job, now=NOW + timedelta(seconds=30))

    recovered, _ = recover_interrupted_job(job, now=NOW + timedelta(seconds=61))
    assert recovered.status is IngestionJobStatus.PENDING
    assert recovered.owner_worker_id is None
    assert recovered.lease_expires_at is None
