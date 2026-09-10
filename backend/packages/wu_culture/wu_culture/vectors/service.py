from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.filters import StructuredSearchFilters
from wu_culture.models import AuthorizedUse, Citation, SourceLevel, SourceType


class VectorIndexError(RuntimeError):
    """Base error for vector index lifecycle and search."""


class VectorIndexNotReady(VectorIndexError):
    """Raised when no compatible ready index exists."""


class VectorIndexConflict(VectorIndexError):
    """Raised for duplicate builds or stale active-state updates."""


class VectorIndexStatus(StrEnum):
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class _VectorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class VectorIndexVersion(_VectorModel):
    id: str = Field(min_length=1, max_length=255)
    release_id: str = Field(min_length=1, max_length=255)
    release_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_model: str = Field(min_length=1, max_length=255)
    embedding_version: str = Field(min_length=1, max_length=128)
    dimensions: int = Field(ge=1, le=65535)
    status: VectorIndexStatus
    item_count: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=4000)
    created_by: str = Field(min_length=1, max_length=255)
    created_at: datetime
    completed_at: datetime | None = None


class VectorIndexState(_VectorModel):
    release_id: str
    active_index_id: str | None = None
    state_version: int = Field(ge=0)
    updated_at: datetime | None = None


class VectorIndexBuildRequest(_VectorModel):
    release_id: str = Field(min_length=1, max_length=255)
    expected_state_version: int = Field(ge=0)


class VectorBuildItem(_VectorModel):
    chunk_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1)


class VectorSearchRequest(_VectorModel):
    query: str = Field(min_length=1, max_length=500)
    release_id: str | None = Field(default=None, min_length=1, max_length=255)
    document_ids: tuple[str, ...] | None = Field(default=None, max_length=100)
    source_levels: tuple[SourceLevel, ...] | None = None
    source_types: tuple[SourceType, ...] | None = None
    authorized_use: AuthorizedUse = AuthorizedUse.PUBLIC_QUOTE
    filters: StructuredSearchFilters = Field(default_factory=StructuredSearchFilters)
    top_k: int = Field(default=10, ge=1, le=100)
    min_similarity: float = Field(default=0.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_filters(self) -> VectorSearchRequest:
        if self.document_ids and len(self.document_ids) != len(set(self.document_ids)):
            raise ValueError("duplicate document filter")
        return self


class VectorSearchHit(_VectorModel):
    release_id: str
    index_id: str
    chunk_id: str
    similarity: float = Field(ge=-1, le=1)
    citation: Citation


class VectorSearchResponse(_VectorModel):
    query: str
    release_id: str
    index_id: str
    embedding_model: str
    embedding_version: str
    hits: tuple[VectorSearchHit, ...]
    message: str = "向量相似度仅用于候选召回，不代表事实可信度"


class VectorIndexRepository(Protocol):
    async def create_build(self, version: VectorIndexVersion, *, expected_state_version: int) -> VectorIndexVersion: ...

    async def complete_build(self, version: VectorIndexVersion, vectors: tuple[tuple[str, tuple[float, ...]], ...]) -> VectorIndexVersion: ...

    async def fail_build(self, version: VectorIndexVersion) -> VectorIndexVersion: ...

    async def get_state(self, release_id: str) -> VectorIndexState: ...

    async def list_versions(self, release_id: str) -> list[VectorIndexVersion]: ...

    async def resolve_search_version(self, release_id: str | None) -> VectorIndexVersion: ...

    async def get_release_build_items(self, release_id: str) -> tuple[str, tuple[VectorBuildItem, ...]]: ...

    async def search_by_vector(self, request: VectorSearchRequest, query_vector: tuple[float, ...]) -> VectorSearchResponse: ...


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")


def begin_vector_index(
    *,
    index_id: str,
    release_id: str,
    release_manifest_sha256: str,
    embedding_model: str,
    embedding_version: str,
    dimensions: int,
    created_by: str,
    created_at: datetime,
) -> VectorIndexVersion:
    _require_aware(created_at, "created_at")
    return VectorIndexVersion(
        id=index_id,
        release_id=release_id,
        release_manifest_sha256=release_manifest_sha256,
        embedding_model=embedding_model,
        embedding_version=embedding_version,
        dimensions=dimensions,
        status=VectorIndexStatus.BUILDING,
        created_by=created_by,
        created_at=created_at,
    )


def complete_vector_index(version: VectorIndexVersion, *, item_count: int, completed_at: datetime) -> VectorIndexVersion:
    if version.status is not VectorIndexStatus.BUILDING:
        raise VectorIndexConflict("only a building vector index can complete")
    if item_count < 1:
        raise ValueError("a ready vector index must contain at least one item")
    _require_aware(completed_at, "completed_at")
    return version.model_copy(
        update={
            "status": VectorIndexStatus.READY,
            "item_count": item_count,
            "completed_at": completed_at,
            "error_code": None,
            "error_message": None,
        }
    )


def fail_vector_index(
    version: VectorIndexVersion,
    *,
    error_code: str,
    error_message: str,
    failed_at: datetime,
) -> VectorIndexVersion:
    if version.status is not VectorIndexStatus.BUILDING:
        raise VectorIndexConflict("only a building vector index can fail")
    _require_aware(failed_at, "failed_at")
    return version.model_copy(
        update={
            "status": VectorIndexStatus.FAILED,
            "error_code": error_code,
            "error_message": error_message,
            "completed_at": failed_at,
        }
    )
