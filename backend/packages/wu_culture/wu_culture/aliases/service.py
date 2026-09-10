from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.filters import Dynasty
from wu_culture.models import EntityType, ReviewStatus


class AliasType(StrEnum):
    HISTORICAL_NAME = "historical_name"
    COLLOQUIAL_NAME = "colloquial_name"
    CHARACTER_VARIANT = "character_variant"
    MODERN_NAME = "modern_name"


class AliasConfidence(StrEnum):
    EVIDENCE_BACKED = "evidence_backed"
    UNVERIFIED = "unverified"


class AliasIndexError(RuntimeError):
    """Raised when a Release alias index is inconsistent or cannot be persisted."""


class _AliasModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AliasRecord(_AliasModel):
    id: str = Field(min_length=1, max_length=255)
    release_id: str = Field(min_length=1, max_length=255)
    entity_id: str = Field(min_length=1, max_length=255)
    canonical_name: str = Field(min_length=1, max_length=255)
    entity_type: EntityType
    alias: str = Field(min_length=1, max_length=255)
    alias_type: AliasType
    applicable_dynasties: tuple[Dynasty, ...] = Field(default=(), max_length=20)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=100)
    review_status: ReviewStatus
    indexed_at: datetime

    @model_validator(mode="after")
    def validate_record(self) -> AliasRecord:
        if _normalize(self.alias) == _normalize(self.canonical_name):
            raise ValueError("alias must differ from canonical_name")
        if len(self.applicable_dynasties) != len(set(self.applicable_dynasties)):
            raise ValueError("duplicate applicable dynasty")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("duplicate alias evidence")
        if any(not evidence_id.strip() for evidence_id in self.evidence_ids):
            raise ValueError("alias evidence ID cannot be empty")
        if self.indexed_at.tzinfo is None or self.indexed_at.utcoffset() is None:
            raise ValueError("indexed_at must include a timezone")
        return self


class AliasExpansionRequest(_AliasModel):
    query: str = Field(min_length=1, max_length=500)
    release_id: str = Field(min_length=1, max_length=255)
    dynasties: tuple[Dynasty, ...] = Field(default=(), max_length=20)
    max_expansions: int = Field(default=5, ge=1, le=20)


class AliasExpansionCandidate(_AliasModel):
    alias_id: str
    matched_alias: str
    entity_id: str
    canonical_name: str
    entity_type: EntityType
    alias_type: AliasType
    applicable_dynasties: tuple[Dynasty, ...]
    evidence_ids: tuple[str, ...]
    confidence: AliasConfidence
    eligible: bool
    reason: str


class AliasExpansionResult(_AliasModel):
    original_query: str
    release_id: str
    resolved_query: str | None
    expanded_terms: tuple[str, ...]
    candidates: tuple[AliasExpansionCandidate, ...]
    requires_disambiguation: bool
    truncated: bool


class AliasRepository(Protocol):
    def list_matching(self, release_id: str, query: str) -> tuple[AliasRecord, ...]: ...


class AsyncAliasRepository(Protocol):
    async def list_matching(self, release_id: str, query: str) -> tuple[AliasRecord, ...]: ...


class InMemoryAliasRepository:
    def __init__(self, records: tuple[AliasRecord, ...] = ()) -> None:
        self._records = records

    def list_matching(self, release_id: str, query: str) -> tuple[AliasRecord, ...]:
        normalized_query = _normalize(query)
        return tuple(record for record in self._records if record.release_id == release_id and _normalize(record.alias) in normalized_query)


class AliasExpansionService:
    def __init__(self, repository: AliasRepository) -> None:
        self._repository = repository

    def expand(self, request: AliasExpansionRequest) -> AliasExpansionResult:
        return expand_alias_records(request, self._repository.list_matching(request.release_id, request.query))


class AsyncAliasExpansionService:
    def __init__(self, repository: AsyncAliasRepository) -> None:
        self._repository = repository

    async def expand(self, request: AliasExpansionRequest) -> AliasExpansionResult:
        records = await self._repository.list_matching(request.release_id, request.query)
        return expand_alias_records(request, records)


def expand_alias_records(
    request: AliasExpansionRequest,
    records: tuple[AliasRecord, ...],
) -> AliasExpansionResult:
    normalized_query = _normalize(request.query)
    ordered = sorted(
        records,
        key=lambda record: (
            normalized_query.find(_normalize(record.alias)),
            -len(_normalize(record.alias)),
            _normalize(record.alias),
            record.entity_id,
            record.id,
        ),
    )[:50]
    prelim: list[tuple[AliasRecord, bool, str]] = []
    for record in ordered:
        if request.dynasties and record.applicable_dynasties and not set(request.dynasties).intersection(record.applicable_dynasties):
            prelim.append((record, False, "dynasty_mismatch"))
        elif not record.evidence_ids:
            prelim.append((record, False, "missing_evidence"))
        elif record.review_status is not ReviewStatus.REVIEWED:
            prelim.append((record, False, "alias_not_reviewed"))
        else:
            prelim.append((record, True, "eligible"))

    eligible_by_alias: dict[str, set[str]] = {}
    for record, eligible, _reason in prelim:
        if eligible:
            eligible_by_alias.setdefault(_normalize(record.alias), set()).add(record.entity_id)
    ambiguous_aliases = {alias for alias, entity_ids in eligible_by_alias.items() if len(entity_ids) > 1}

    candidates = []
    expandable: list[AliasRecord] = []
    for record, eligible, reason in prelim:
        if eligible and _normalize(record.alias) in ambiguous_aliases:
            eligible = False
            reason = "ambiguous_alias"
        if eligible:
            expandable.append(record)
        candidates.append(
            AliasExpansionCandidate(
                alias_id=record.id,
                matched_alias=record.alias,
                entity_id=record.entity_id,
                canonical_name=record.canonical_name,
                entity_type=record.entity_type,
                alias_type=record.alias_type,
                applicable_dynasties=record.applicable_dynasties,
                evidence_ids=record.evidence_ids,
                confidence=AliasConfidence.EVIDENCE_BACKED if record.evidence_ids and record.review_status is ReviewStatus.REVIEWED else AliasConfidence.UNVERIFIED,
                eligible=eligible,
                reason=reason,
            )
        )

    selected = expandable[: request.max_expansions]
    resolved_query = unicodedata.normalize("NFKC", request.query)
    expanded_terms = []
    for record in selected:
        resolved_query = re.sub(
            re.escape(unicodedata.normalize("NFKC", record.alias)),
            lambda _match: record.canonical_name,
            resolved_query,
            count=1,
            flags=re.IGNORECASE,
        )
        expanded_terms.append(record.canonical_name)
    requires_disambiguation = bool(ambiguous_aliases)
    return AliasExpansionResult(
        original_query=request.query,
        release_id=request.release_id,
        resolved_query=None if requires_disambiguation else resolved_query,
        expanded_terms=tuple(expanded_terms),
        candidates=tuple(candidates),
        requires_disambiguation=requires_disambiguation,
        truncated=len(expandable) > len(selected),
    )


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()
