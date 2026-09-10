from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ConflictType(StrEnum):
    YEAR = "year"
    PERSON = "person"
    PLACE = "place"
    TEXT = "text"
    NONE = "none"


class UncertaintyLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    NONE = "none"


class _ConflictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ClaimVariant(_ConflictModel):
    evidence_id: str
    document_title: str
    edition: str | None = None
    volume: str | None = None
    page_start: int
    page_end: int
    source_level: str
    review_status: str
    claim_text: str
    year_mentions: tuple[str, ...] = ()
    person_mentions: tuple[str, ...] = ()
    place_mentions: tuple[str, ...] = ()


class ConflictCluster(_ConflictModel):
    conflict_type: ConflictType
    topic: str
    summary: str
    uncertainty: UncertaintyLevel
    variants: tuple[ClaimVariant, ...]
    diff_snippets: tuple[str, ...] = ()


class ConflictReport(_ConflictModel):
    schema_version: Literal["conflict-report-v1"] = "conflict-report-v1"
    release_id: str
    has_conflicts: bool
    uncertainty: UncertaintyLevel
    clusters: tuple[ConflictCluster, ...]
    retained_low_grade: bool = False
    notes: tuple[str, ...] = ()
