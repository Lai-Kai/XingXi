from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from wu_culture.models import ReviewStatus


class RelationType(StrEnum):
    LOCATED_IN = "located_in"
    BUILT_BY = "built_by"
    REPAIRED_IN = "repaired_in"
    CROSSES = "crosses"
    RELATED_TO = "related_to"
    SIBLING_OF = "sibling_of"
    SPOUSE_OF = "spouse_of"
    PARENT_OF = "parent_of"
    LIVED_IN = "lived_in"
    VISITED = "visited"
    BORN_IN = "born_in"
    WORKED_AT = "worked_at"
    STUDIED_AT = "studied_at"
    DIED_AT = "died_at"
    COMPOSED_AT = "composed_at"
    MENTIONED_IN_POETRY = "mentioned_in_poetry"
    DOCUMENTED_IN = "documented_in"


class RelationValidationError(ValueError):
    pass


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class RelationRecord(_M):
    id: str = Field(min_length=1, max_length=255)
    subject_id: str = Field(min_length=1, max_length=255)
    relation_type: RelationType
    object_id: str = Field(min_length=1, max_length=255)
    start_time: str | None = None
    end_time: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = ()
    is_inferred: bool = False
    review_status: ReviewStatus = ReviewStatus.PENDING
    release_id: str | None = None


class RelationCreate(_M):
    id: str | None = None
    subject_id: str = Field(min_length=1, max_length=255)
    relation_type: RelationType
    object_id: str = Field(min_length=1, max_length=255)
    start_time: str | None = None
    end_time: str | None = None
    confidence: float = Field(default=0.7, ge=0, le=1)
    evidence_ids: tuple[str, ...] = ()
    is_inferred: bool = False
    review_status: ReviewStatus = ReviewStatus.PENDING
    release_id: str | None = None


class RelationQuery(_M):
    entity_id: str
    direction: Literal["out", "in", "both"] = "both"
    limit: int = Field(default=50, ge=1, le=200)


class RelationService:
    def __init__(self) -> None:
        self._items: dict[str, RelationRecord] = {}

    def create(self, payload: RelationCreate) -> RelationRecord:
        if payload.subject_id == payload.object_id:
            raise RelationValidationError("subject and object must differ")
        if not payload.evidence_ids and not payload.is_inferred:
            raise RelationValidationError("relation requires evidence_ids or is_inferred=true")
        if len(payload.evidence_ids) != len(set(payload.evidence_ids)) or any(not item.strip() for item in payload.evidence_ids):
            raise RelationValidationError("relation evidence IDs must be unique and non-empty")
        # duplicate check
        for item in self._items.values():
            if (
                item.subject_id == payload.subject_id
                and item.object_id == payload.object_id
                and item.relation_type is payload.relation_type
            ):
                raise RelationValidationError("duplicate relation")
        record = RelationRecord(
            id=payload.id or f"rel-{uuid.uuid4().hex[:10]}",
            subject_id=payload.subject_id,
            relation_type=payload.relation_type,
            object_id=payload.object_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            confidence=payload.confidence,
            evidence_ids=payload.evidence_ids,
            is_inferred=payload.is_inferred,
            review_status=payload.review_status,
            release_id=payload.release_id,
        )
        if record.id in self._items:
            raise RelationValidationError(f"relation already exists: {record.id}")
        self._items[record.id] = record
        return record

    def one_hop(self, query: RelationQuery) -> list[RelationRecord]:
        rows: list[RelationRecord] = []
        for item in self._items.values():
            if query.direction in {"out", "both"} and item.subject_id == query.entity_id:
                rows.append(item)
            if query.direction in {"in", "both"} and item.object_id == query.entity_id:
                rows.append(item)
        rows.sort(key=lambda row: row.id)
        return rows[: query.limit]
