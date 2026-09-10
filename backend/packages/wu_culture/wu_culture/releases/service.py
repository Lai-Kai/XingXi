from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeReleaseError(RuntimeError):
    """Base error for knowledge release operations."""


class KnowledgeReleaseNotFound(KnowledgeReleaseError):
    """Raised when a release or manifest input does not exist."""


class KnowledgeReleaseGateError(KnowledgeReleaseError):
    """Raised when unreviewed content is requested for publication."""


class KnowledgeReleaseConflict(KnowledgeReleaseError):
    """Raised when the active pointer changed concurrently."""


class KnowledgeReleasePreparationError(KnowledgeReleaseError):
    """Raised when indexes or versioned assets cannot be prepared."""

    def __init__(self, release_id: str, message: str) -> None:
        super().__init__(message)
        self.release_id = release_id


class ReleaseAction(StrEnum):
    PUBLISH = "publish"
    ACTIVATE = "activate"
    ROLLBACK = "rollback"


class ReleaseStatus(StrEnum):
    PREPARING = "preparing"
    READY = "ready"
    FAILED = "failed"
    ACTIVE = "active"


class _ReleaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class KnowledgeReleaseItem(_ReleaseModel):
    ordinal: int = Field(ge=0)
    document_id: str = Field(min_length=1, max_length=255)
    source_file_id: str = Field(min_length=1, max_length=255)
    chunk_set_id: str = Field(min_length=1, max_length=255)
    chunk_id: str = Field(min_length=1, max_length=255)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cleaned_page_ids: tuple[str, ...] = Field(min_length=1)


class KnowledgeRelease(_ReleaseModel):
    id: str = Field(min_length=1, max_length=255)
    version_number: int = Field(ge=1)
    version: str = Field(pattern=r"^v[1-9][0-9]*$")
    release_notes: str = Field(min_length=1, max_length=4000)
    scope: Literal["public", "internal"] = "public"
    status: ReleaseStatus = ReleaseStatus.PREPARING
    failure_code: str | None = None
    failure_message: str | None = None
    preparation_attempts: int = Field(default=0, ge=0)
    ready_at: datetime | None = None
    activated_at: datetime | None = None
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: tuple[KnowledgeReleaseItem, ...] = Field(min_length=1)
    created_by: str = Field(min_length=1, max_length=255)
    created_at: datetime


class KnowledgeReleaseSummary(_ReleaseModel):
    """Release metadata for request paths that do not consume the manifest."""

    id: str = Field(min_length=1, max_length=255)
    version_number: int = Field(ge=1)
    version: str = Field(pattern=r"^v[1-9][0-9]*$")
    scope: Literal["public", "internal"] = "public"
    status: ReleaseStatus
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    item_count: int = Field(ge=1)
    created_at: datetime


class KnowledgeReleaseState(_ReleaseModel):
    active_release_id: str | None = None
    active_version: str | None = None
    state_version: int = Field(ge=0)
    updated_by: str | None = None
    updated_at: datetime | None = None


class KnowledgeReleaseEvent(_ReleaseModel):
    id: str = Field(min_length=1, max_length=255)
    action: ReleaseAction
    previous_release_id: str | None = None
    new_release_id: str = Field(min_length=1, max_length=255)
    state_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)
    actor_id: str = Field(min_length=1, max_length=255)
    created_at: datetime


class PublishReleaseRequest(_ReleaseModel):
    chunk_set_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    release_notes: str = Field(min_length=1, max_length=4000)
    expected_state_version: int = Field(ge=0)
    activate: bool = True
    scope: Literal["public", "internal"] = "public"

    @model_validator(mode="after")
    def validate_unique_chunk_sets(self) -> PublishReleaseRequest:
        if len(self.chunk_set_ids) != len(set(self.chunk_set_ids)):
            raise ValueError("duplicate chunk set in release manifest")
        return self


class ActivateReleaseRequest(_ReleaseModel):
    release_id: str = Field(min_length=1, max_length=255)
    expected_state_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=4000)


class RollbackReleaseRequest(_ReleaseModel):
    expected_state_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=4000)
    target_release_id: str | None = Field(default=None, min_length=1, max_length=255)


class RetryReleaseRequest(_ReleaseModel):
    expected_state_version: int = Field(ge=0)
    activate: bool = True


class KnowledgeReleaseRepository(Protocol):
    async def publish(self, request: PublishReleaseRequest, *, actor_id: str, created_at: datetime) -> KnowledgeRelease: ...

    async def list_releases(self) -> list[KnowledgeRelease]: ...

    async def get(self, release_id: str) -> KnowledgeRelease | None: ...

    async def get_state(self) -> KnowledgeReleaseState: ...

    async def get_active(self) -> KnowledgeRelease | None: ...

    async def get_summary(self, release_id: str) -> KnowledgeReleaseSummary | None: ...

    async def get_active_summary(self) -> KnowledgeReleaseSummary | None: ...

    async def activate(self, request: ActivateReleaseRequest, *, actor_id: str, changed_at: datetime) -> KnowledgeReleaseState: ...

    async def rollback(self, request: RollbackReleaseRequest, *, actor_id: str, changed_at: datetime) -> KnowledgeReleaseState: ...

    async def retry(self, release_id: str, request: RetryReleaseRequest, *, actor_id: str, changed_at: datetime) -> KnowledgeRelease: ...

    async def list_events(self) -> list[KnowledgeReleaseEvent]: ...


def calculate_manifest_sha256(items: tuple[KnowledgeReleaseItem, ...]) -> str:
    payload = [item.model_dump(mode="json") for item in items]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_knowledge_release(
    *,
    release_id: str,
    version_number: int,
    release_notes: str,
    scope: Literal["public", "internal"] = "public",
    items: tuple[KnowledgeReleaseItem, ...],
    created_by: str,
    created_at: datetime,
    status: ReleaseStatus = ReleaseStatus.PREPARING,
) -> KnowledgeRelease:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must include a timezone")
    ordered = tuple(item.model_copy(update={"ordinal": index}) for index, item in enumerate(items))
    return KnowledgeRelease(
        id=release_id,
        version_number=version_number,
        version=f"v{version_number}",
        release_notes=release_notes,
        scope=scope,
        status=status,
        manifest_sha256=calculate_manifest_sha256(ordered),
        items=ordered,
        created_by=created_by,
        created_at=created_at,
    )
