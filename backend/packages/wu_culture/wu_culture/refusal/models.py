from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RefusalReason(StrEnum):
    EMPTY_RESULTS = "empty_results"
    INSUFFICIENT_PACK = "insufficient_pack"
    LOW_GRADE_ONLY = "low_grade_only"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NONE = "none"


class _RefusalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class RefusalDecision(_RefusalModel):
    should_refuse: bool
    reason: RefusalReason
    search_status: str
    query: str
    release_id: str | None = None
    document_scope: tuple[str, ...] = ()
    evidence_count: int = Field(ge=0)
    usable_evidence_count: int = Field(ge=0)
    allowed_source_levels: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


class RefusalResponse(_RefusalModel):
    schema_version: Literal["refusal-v1"] = "refusal-v1"
    decision: RefusalDecision
    message: str
    search_scope_summary: str
    next_steps: tuple[str, ...]
    text: str
