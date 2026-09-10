from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.models import ReviewStatus


class ReviewTargetNotFound(ValueError):
    """Raised when a review target is missing or outside the source file."""


class ReviewConflictError(RuntimeError):
    """Raised when concurrent reviewers attempt the same target revision."""


class ReviewTargetType(StrEnum):
    PAGE = "page"
    CHUNK = "chunk"


class _ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ReviewRequest(_ReviewModel):
    target_type: ReviewTargetType
    target_id: str = Field(min_length=1, max_length=255)
    decision: ReviewStatus
    comment: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_decision(self) -> ReviewRequest:
        if self.decision is ReviewStatus.PENDING:
            raise ValueError("pending is not a review decision")
        if self.decision in {ReviewStatus.REJECTED, ReviewStatus.DISPUTED} and not self.comment:
            raise ValueError("comment is required for rejected or disputed review")
        return self


class ReviewBatchRequest(_ReviewModel):
    items: tuple[ReviewRequest, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_targets(self) -> ReviewBatchRequest:
        identities = [(item.target_type, item.target_id) for item in self.items]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate review target in one batch")
        return self


class ReviewRecord(_ReviewModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_file_id: str = Field(min_length=1)
    target_type: ReviewTargetType
    target_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    previous_status: ReviewStatus
    decision: ReviewStatus
    comment: str | None = None
    batch_id: str | None = None
    reviewed_by: str = Field(min_length=1)
    reviewed_at: datetime


class PublicationGateDecision(_ReviewModel):
    allowed: bool
    reasons: tuple[str, ...]


class ReviewPageTarget(_ReviewModel):
    id: str
    page_number: int = Field(ge=1)
    folio_label: str | None = None
    generation_number: int = Field(ge=1)
    raw_text: str
    clean_text: str
    review_status: ReviewStatus
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    rotation_degrees: int
    cleaning_change_count: int = Field(ge=0)


class ReviewChunkTarget(_ReviewModel):
    id: str
    chunk_index: int = Field(ge=0)
    volume: str | None = None
    item: str | None = None
    raw_text: str
    clean_text: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    cleaned_page_ids: tuple[str, ...]
    review_status: ReviewStatus


class ReviewQueue(_ReviewModel):
    document_id: str
    source_file_id: str
    chunk_set_id: str
    split_version: str
    pages: tuple[ReviewPageTarget, ...]
    chunks: tuple[ReviewChunkTarget, ...]


class ReviewRepository(Protocol):
    async def review_many(
        self,
        *,
        document_id: str,
        source_file_id: str,
        batch: ReviewBatchRequest,
        reviewed_by: str,
        reviewed_at: datetime,
        batch_id: str,
    ) -> list[ReviewRecord]: ...

    async def list_records(
        self,
        *,
        source_file_id: str,
        target_type: ReviewTargetType | None = None,
        target_id: str | None = None,
    ) -> list[ReviewRecord]: ...

    async def publication_gate(self, *, source_file_id: str, chunk_id: str) -> PublicationGateDecision: ...

    async def chunk_set_publication_gate(self, *, source_file_id: str, chunk_set_id: str) -> PublicationGateDecision: ...

    async def get_queue(self, *, source_file_id: str, chunk_set_id: str) -> ReviewQueue: ...


def build_review_record(
    *,
    record_id: str,
    document_id: str,
    source_file_id: str,
    request: ReviewRequest,
    previous_status: ReviewStatus,
    revision: int,
    reviewed_by: str,
    reviewed_at: datetime,
    batch_id: str | None = None,
) -> ReviewRecord:
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone")
    return ReviewRecord(
        id=record_id,
        document_id=document_id,
        source_file_id=source_file_id,
        target_type=request.target_type,
        target_id=request.target_id,
        revision=revision,
        previous_status=previous_status,
        decision=request.decision,
        comment=request.comment,
        batch_id=batch_id,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
    )


def evaluate_publication_gate(
    *,
    chunk_status: ReviewStatus,
    page_statuses: tuple[ReviewStatus, ...],
) -> PublicationGateDecision:
    reasons = []
    if chunk_status is not ReviewStatus.REVIEWED:
        reasons.append("chunk_not_reviewed")
    if not page_statuses or any(status is not ReviewStatus.REVIEWED for status in page_statuses):
        reasons.append("page_not_reviewed")
    return PublicationGateDecision(allowed=not reasons, reasons=tuple(reasons))
