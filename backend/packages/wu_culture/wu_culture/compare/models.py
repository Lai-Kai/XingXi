from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _CompareModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CompareSourcesRequest(_CompareModel):
    topic: str = Field(min_length=1, max_length=500)
    document_ids: tuple[str, ...] | None = Field(default=None, max_length=20)
    release_id: str | None = None
    max_items_per_document: int = Field(default=3, ge=1, le=10)
    max_quote_chars: int = Field(default=800, ge=80, le=5000)


class SourceColumn(_CompareModel):
    evidence_id: str
    document_id: str
    document_title: str
    edition: str | None = None
    volume: str | None = None
    section: str | None = None
    page_start: int
    page_end: int
    source_level: str
    review_status: str
    quote: str
    quote_truncated: bool = False
    original_quote_chars: int


class ComparePairDiff(_CompareModel):
    left_evidence_id: str
    right_evidence_id: str
    common_points: tuple[str, ...]
    differences: tuple[str, ...]
    diff_snippets: tuple[str, ...]


class CompareSourcesResult(_CompareModel):
    schema_version: Literal["compare-sources-v1"] = "compare-sources-v1"
    topic: str
    release_id: str | None = None
    status: Literal["ready", "single_source", "empty", "truncated"]
    columns: tuple[SourceColumn, ...]
    pair_diffs: tuple[ComparePairDiff, ...]
    open_questions: tuple[str, ...]
    notes: tuple[str, ...] = ()
    export: dict
