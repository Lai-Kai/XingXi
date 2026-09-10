from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.models import ReviewStatus, SourceLevel


class EvidencePackStatus(StrEnum):
    READY = "ready"
    EMPTY = "empty"
    INSUFFICIENT_BUDGET = "insufficient_budget"


class _EvidencePackModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EvidencePackConfig(_EvidencePackModel):
    """Budget and clipping limits for prompt-facing evidence packs."""

    token_budget: int = Field(default=4000, ge=1, le=100_000)
    max_items: int = Field(default=12, ge=1, le=100)
    max_quote_tokens: int = Field(default=512, ge=1, le=20_000)
    min_quote_tokens: int = Field(default=24, ge=1, le=2_000)

    @model_validator(mode="after")
    def validate_limits(self) -> EvidencePackConfig:
        if self.min_quote_tokens > self.max_quote_tokens:
            raise ValueError("min_quote_tokens must not exceed max_quote_tokens")
        return self


class EvidencePackItem(_EvidencePackModel):
    """One packed citation. Only ``quote`` may be truncated; metadata stays intact."""

    rank: int = Field(ge=1)
    evidence_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_file_id: str | None = None
    document_title: str = Field(min_length=1)
    edition: str | None = None
    volume: str | None = None
    section: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    folio_start: str | None = None
    folio_end: str | None = None
    quote: str = Field(min_length=1)
    quote_provenance: Literal["verbatim", "truncated_verbatim"]
    quote_truncated: bool
    original_quote_chars: int = Field(ge=1)
    original_quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_level: SourceLevel
    review_status: ReviewStatus

    @model_validator(mode="after")
    def validate_item(self) -> EvidencePackItem:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        if self.quote_truncated and self.quote_provenance != "truncated_verbatim":
            raise ValueError("truncated quotes must use truncated_verbatim provenance")
        if not self.quote_truncated and self.quote_provenance != "verbatim":
            raise ValueError("full quotes must use verbatim provenance")
        if self.quote_truncated and not self.quote.endswith("…"):
            raise ValueError("truncated quotes must end with ellipsis marker")
        return self


class EvidencePack(_EvidencePackModel):
    """Stable, serializable evidence pack contract for answers and tools."""

    schema_version: Literal["evidence-pack-v1"] = "evidence-pack-v1"
    release_id: str = Field(min_length=1)
    status: EvidencePackStatus
    token_budget: int = Field(ge=1)
    used_tokens: int = Field(ge=0)
    input_count: int = Field(ge=0)
    deduplicated_count: int = Field(ge=0)
    omitted_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    items: tuple[EvidencePackItem, ...]

    @model_validator(mode="after")
    def validate_pack(self) -> EvidencePack:
        if self.used_tokens > self.token_budget:
            raise ValueError("used_tokens must not exceed token_budget")
        if self.status is EvidencePackStatus.READY and not self.items:
            raise ValueError("ready packs must contain items")
        if self.status is not EvidencePackStatus.READY and self.items:
            raise ValueError("non-ready packs must not contain items")
        if self.document_count != len({item.document_id for item in self.items}):
            raise ValueError("document_count must match unique document ids in items")
        ranks = [item.rank for item in self.items]
        if ranks != sorted(ranks):
            raise ValueError("items must be ordered by original rank ascending")
        return self

    def to_canonical_json(self) -> str:
        """Serialize deterministically for prompts, caches, and audit logs."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def allowed_evidence_ids(self) -> frozenset[str]:
        return frozenset(item.evidence_id for item in self.items)
