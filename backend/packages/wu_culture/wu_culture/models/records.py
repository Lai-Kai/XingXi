from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceLevel(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    U = "U"


class SourceType(StrEnum):
    GAZETTEER = "gazetteer"
    INSCRIPTION = "inscription"
    ARCHIVE = "archive"
    HERITAGE_RECORD = "heritage_record"
    SCHOLARLY_WORK = "scholarly_work"
    ORAL_HISTORY = "oral_history"
    WEB = "web"
    INFERENCE = "inference"
    OTHER = "other"


class CopyrightStatus(StrEnum):
    PUBLIC_DOMAIN = "public_domain"
    AUTHORIZED = "authorized"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class SourceDocumentStatus(StrEnum):
    REGISTERED = "registered"
    ARCHIVED = "archived"


class AuthorizationStatus(StrEnum):
    UNCONFIRMED = "unconfirmed"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AuthorizedUse(StrEnum):
    INTERNAL_PROCESSING = "internal_processing"
    PUBLIC_FULL_TEXT = "public_full_text"
    PUBLIC_QUOTE = "public_quote"


class VisibilityScope(StrEnum):
    INTERNAL = "internal"
    AUTHENTICATED = "authenticated"
    PUBLIC = "public"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class EntityType(StrEnum):
    PERSON = "person"
    FAMILY = "family"
    PLACE = "place"
    WATERWAY = "waterway"
    BRIDGE = "bridge"
    BUILDING = "building"
    GARDEN = "garden"
    RELIC = "relic"
    ORGANIZATION = "organization"
    WORK = "work"
    EVENT = "event"


class SearchStatus(StrEnum):
    SUPPORTED = "supported"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"
    INFERRED = "inferred"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceDocument(DomainModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    edition: str | None = None
    source_type: SourceType
    source_type_label: str | None = Field(default=None, min_length=1, max_length=100)
    source_level: SourceLevel
    copyright_status: CopyrightStatus
    source_institution: str = Field(default="unknown", min_length=1)
    holder: str = Field(default="unknown", min_length=1)
    status: SourceDocumentStatus = SourceDocumentStatus.REGISTERED
    authorization_status: AuthorizationStatus = AuthorizationStatus.UNCONFIRMED
    authorization_basis: str | None = None
    authorization_valid_from: datetime | None = None
    authorization_valid_until: datetime | None = None
    visibility_scope: VisibilityScope = VisibilityScope.INTERNAL
    authorized_uses: tuple[AuthorizedUse, ...] = ()
    authorization_proof_object_key: str | None = None
    file_hash: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_authorization_policy(self) -> SourceDocument:
        if self.source_type is SourceType.OTHER and not self.source_type_label:
            raise ValueError("source_type_label is required when source_type is other")
        if self.source_type is not SourceType.OTHER and self.source_type_label is not None:
            raise ValueError("source_type_label is only allowed when source_type is other")
        for name in ("authorization_valid_from", "authorization_valid_until"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must include a timezone")
        if self.authorization_valid_from is not None and self.authorization_valid_until is not None and self.authorization_valid_until <= self.authorization_valid_from:
            raise ValueError("authorization_valid_until must be after authorization_valid_from")
        if self.authorization_status is AuthorizationStatus.ACTIVE:
            if not self.authorization_basis:
                raise ValueError("active authorization requires authorization_basis")
            if not self.authorized_uses:
                raise ValueError("active authorization requires at least one authorized use")
        if self.authorization_status is AuthorizationStatus.UNCONFIRMED and self.authorized_uses:
            raise ValueError("unconfirmed authorization cannot grant uses")
        return self


class SourceAccessDecision(DomainModel):
    use: AuthorizedUse
    allowed: bool
    reason: str
    effective_status: AuthorizationStatus


class SourceAuthorizationEvent(DomainModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    previous_status: AuthorizationStatus
    new_status: AuthorizationStatus
    previous_copyright_status: CopyrightStatus
    new_copyright_status: CopyrightStatus
    new_visibility_scope: VisibilityScope
    new_authorized_uses: tuple[AuthorizedUse, ...]
    authorization_valid_until: datetime | None = None
    authorization_proof_object_key: str | None = None
    changed_by: str = Field(min_length=1)
    changed_at: datetime
    reason: str = Field(min_length=1)


class SourceFile(DomainModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    size: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duplicate_of_file_id: str | None = None
    version_of_file_id: str | None = None
    uploaded_by: str = Field(min_length=1)
    uploaded_at: datetime


class TextChunk(DomainModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    volume: str | None = None
    section: str | None = None
    paragraph: str | None = None
    original_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    review_status: ReviewStatus = ReviewStatus.PENDING

    @model_validator(mode="after")
    def validate_page_range(self) -> TextChunk:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class Evidence(DomainModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    source_level: SourceLevel
    review_status: ReviewStatus


class EvidenceRecord(DomainModel):
    document: SourceDocument
    chunk: TextChunk
    evidence: Evidence

    @model_validator(mode="after")
    def validate_references(self) -> EvidenceRecord:
        if self.chunk.document_id != self.document.id:
            raise ValueError("chunk.document_id must reference document.id")
        if self.evidence.document_id != self.document.id:
            raise ValueError("evidence.document_id must reference document.id")
        if self.evidence.chunk_id != self.chunk.id:
            raise ValueError("evidence.chunk_id must reference chunk.id")
        if self.evidence.source_level != self.document.source_level:
            raise ValueError("evidence.source_level must match document.source_level")
        return self


class Entity(DomainModel):
    id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    entity_type: EntityType
    dynasty: str | None = None
    extant_status: str | None = None
    summary: str | None = None
    review_status: ReviewStatus = ReviewStatus.PENDING
    evidence_ids: list[str] = Field(default_factory=list)
    release_id: str | None = None


class EntityAlias(DomainModel):
    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    alias_type: str | None = None
    valid_period: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class HistoricalRelation(DomainModel):
    id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    start_time: str | None = None
    end_time: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1)


class SearchFilters(DomainModel):
    document_ids: list[str] | None = None
    source_levels: list[SourceLevel] | None = None
    source_types: list[SourceType] | None = None
    reviewed_only: bool = True


class SearchRequest(DomainModel):
    query: str = Field(min_length=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(default=5, ge=1, le=20)


class Citation(DomainModel):
    evidence_id: str
    document_id: str
    source_file_id: str | None = None
    document_title: str
    edition: str | None = None
    volume: str | None = None
    section: str | None = None
    page_start: int
    page_end: int
    folio_start: str | None = None
    folio_end: str | None = None
    quote: str
    source_level: SourceLevel
    review_status: ReviewStatus


class SearchHit(DomainModel):
    chunk_id: str = Field(min_length=1)
    score: float = Field(ge=0)
    matched_terms: list[str]
    citation: Citation


class SearchResponse(DomainModel):
    query: str
    status: SearchStatus
    hits: list[SearchHit]
    message: str
