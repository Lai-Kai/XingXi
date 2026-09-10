from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from wu_culture.models import EntityType, ReviewStatus


class _EntityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EntityRecord(_EntityModel):
    id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1, max_length=255)
    entity_type: EntityType
    dynasty: str | None = Field(default=None, max_length=64)
    extant_status: str | None = Field(default=None, max_length=64)
    summary: str | None = Field(default=None, max_length=4000)
    review_status: ReviewStatus = ReviewStatus.PENDING
    release_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EntityDetail(EntityRecord):
    schema_version: Literal["entity-detail-v1"] = "entity-detail-v1"
    evidence: tuple[dict, ...] = ()


class EntityCreate(_EntityModel):
    id: str | None = Field(default=None, min_length=1, max_length=255)
    canonical_name: str = Field(min_length=1, max_length=255)
    entity_type: EntityType
    dynasty: str | None = Field(default=None, max_length=64)
    extant_status: str | None = Field(default=None, max_length=64)
    summary: str | None = Field(default=None, max_length=4000)
    review_status: ReviewStatus = ReviewStatus.PENDING
    release_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


class EntityUpdate(_EntityModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=255)
    entity_type: EntityType | None = None
    dynasty: str | None = Field(default=None, max_length=64)
    extant_status: str | None = Field(default=None, max_length=64)
    summary: str | None = Field(default=None, max_length=4000)
    review_status: ReviewStatus | None = None
    evidence_ids: tuple[str, ...] | None = None
