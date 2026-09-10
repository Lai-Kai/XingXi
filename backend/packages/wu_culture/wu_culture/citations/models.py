from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _CitationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AnswerCitation(_CitationModel):
    """One stable, evidence-backed inline citation slot."""

    number: int = Field(ge=1)
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
    source_level: str = Field(min_length=1)
    review_status: str = Field(min_length=1)
    href: str = Field(min_length=1)

    @field_validator("href")
    @classmethod
    def validate_href(cls, value: str) -> str:
        if not value.lower().startswith("evidence://"):
            raise ValueError("href must use evidence:// protocol")
        evidence_id = value.split("://", 1)[1].split("?", 1)[0].split("#", 1)[0].strip("/")
        if not evidence_id:
            raise ValueError("href must include evidence id")
        return value

    @model_validator(mode="after")
    def validate_locator(self) -> AnswerCitation:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        href_id = self.href.split("://", 1)[1].split("?", 1)[0].split("#", 1)[0].strip("/")
        if href_id != self.evidence_id:
            raise ValueError("href evidence id must match evidence_id")
        return self

    @property
    def locator_label(self) -> str:
        parts = [self.document_title]
        if self.volume:
            parts.append(self.volume)
        if self.page_start == self.page_end:
            parts.append(f"p.{self.page_start}")
        else:
            parts.append(f"p.{self.page_start}-{self.page_end}")
        return " ".join(parts)


class CitationContract(_CitationModel):
    """Stable numbering map from an evidence pack to answer citations."""

    schema_version: Literal["answer-citation-v1"] = "answer-citation-v1"
    release_id: str = Field(min_length=1)
    citations: tuple[AnswerCitation, ...]

    @model_validator(mode="after")
    def validate_contract(self) -> CitationContract:
        numbers = [item.number for item in self.citations]
        evidence_ids = [item.evidence_id for item in self.citations]
        if numbers != sorted(numbers):
            raise ValueError("citations must be ordered by number ascending")
        if len(numbers) != len(set(numbers)):
            raise ValueError("citation numbers must be unique")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("citation evidence_ids must be unique")
        expected = list(range(1, len(self.citations) + 1))
        if numbers and numbers != expected:
            raise ValueError("citation numbers must be contiguous starting at 1")
        return self

    def by_number(self) -> dict[int, AnswerCitation]:
        return {item.number: item for item in self.citations}

    def by_evidence_id(self) -> dict[str, AnswerCitation]:
        return {item.evidence_id: item for item in self.citations}

    def allowed_evidence_ids(self) -> frozenset[str]:
        return frozenset(item.evidence_id for item in self.citations)

    def to_canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class RejectedCitation(_CitationModel):
    raw: str
    reason: Literal[
        "unknown_evidence_id",
        "unknown_number",
        "missing_evidence_id",
        "malformed",
    ]
    claimed_evidence_id: str | None = None
    claimed_number: int | None = None


class CitationValidationResult(_CitationModel):
    schema_version: Literal["answer-citation-validation-v1"] = "answer-citation-validation-v1"
    original_text: str
    sanitized_text: str
    valid_refs: tuple[AnswerCitation, ...]
    rejected: tuple[RejectedCitation, ...]
    rewritten: bool

    @property
    def is_valid(self) -> bool:
        return not self.rejected and not self.rewritten


class EvidenceDetail(_CitationModel):
    """Detail payload opened from an evidence:// deep link."""

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
    source_level: str = Field(min_length=1)
    review_status: str = Field(min_length=1)
    href: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_detail(self) -> EvidenceDetail:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        if not self.href.lower().startswith("evidence://"):
            raise ValueError("href must use evidence:// protocol")
        href_id = self.href.split("://", 1)[1].split("?", 1)[0].split("#", 1)[0].strip("/")
        if href_id != self.evidence_id:
            raise ValueError("href evidence id must match evidence_id")
        return self
