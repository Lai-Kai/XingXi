from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.models import EvidenceRecord, ReviewStatus, SourceLevel


class AuthorityDecision(StrEnum):
    SELECTED = "selected"
    NEEDS_REVIEW = "needs_review"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class NameVariantInput(_Model):
    name: str = Field(min_length=1, max_length=255)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> NameVariantInput:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique within a name variant")
        return self


class NameAuthorityRequest(_Model):
    variants: tuple[NameVariantInput, ...] = Field(min_length=2, max_length=20)
    research_context: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_variants(self) -> NameAuthorityRequest:
        names = [variant.name.casefold() for variant in self.variants]
        if len(names) != len(set(names)):
            raise ValueError("variant names must be unique")
        return self


class AuthorityEvidence(_Model):
    evidence_id: str
    document_id: str
    document_title: str
    edition: str | None
    source_level: SourceLevel
    review_status: ReviewStatus
    page_start: int
    page_end: int
    contributes_to_score: bool


class NameAuthorityCandidate(_Model):
    name: str
    score: float = Field(ge=0, le=100)
    eligible: bool
    best_source_level: SourceLevel | None
    reviewed_document_count: int = Field(ge=0)
    evidence: tuple[AuthorityEvidence, ...]
    missing_evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]


class NameAuthorityResolution(_Model):
    decision: AuthorityDecision
    preferred_name: str | None
    confidence: str
    research_context: str | None
    candidates: tuple[NameAuthorityCandidate, ...]
    retained_names: tuple[str, ...]
    explanation: str
    requires_human_review: bool


class EvidenceLookup(Protocol):
    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None: ...


_AUTHORITY_SCORE = {
    SourceLevel.A: 100.0,
    SourceLevel.B: 80.0,
    SourceLevel.C: 60.0,
    SourceLevel.D: 30.0,
    SourceLevel.E: 10.0,
    SourceLevel.U: 0.0,
}


class NameAuthorityService:
    """Resolve a preferred name from reviewed evidence without deleting variants."""

    def __init__(self, evidence_repository: EvidenceLookup) -> None:
        self._evidence_repository = evidence_repository

    async def resolve(self, request: NameAuthorityRequest) -> NameAuthorityResolution:
        assessments = [await self._assess(variant) for variant in request.variants]
        ordered = sorted(assessments, key=lambda item: (-item.score, item.name.casefold()))
        eligible = [candidate for candidate in ordered if candidate.eligible]
        retained_names = tuple(candidate.name for candidate in ordered)
        if not eligible:
            return NameAuthorityResolution(
                decision=AuthorityDecision.INSUFFICIENT_EVIDENCE,
                preferred_name=None,
                confidence="none",
                research_context=request.research_context,
                candidates=tuple(ordered),
                retained_names=retained_names,
                explanation="所有候选名称都缺少已审核证据，不能自动确定首选名称。",
                requires_human_review=True,
            )

        winner = eligible[0]
        runner_up = eligible[1] if len(eligible) > 1 else None
        margin = winner.score - runner_up.score if runner_up is not None else winner.score
        if runner_up is not None and margin < 10:
            return NameAuthorityResolution(
                decision=AuthorityDecision.NEEDS_REVIEW,
                preferred_name=None,
                confidence="low",
                research_context=request.research_context,
                candidates=tuple(ordered),
                retained_names=retained_names,
                explanation=(f"“{winner.name}”与“{runner_up.name}”的权威评分差距不足 10 分，系统保留全部异名并交由人工结合时代语境复核。"),
                requires_human_review=True,
            )

        confidence = "high" if winner.score >= 80 and margin >= 15 else "medium"
        return NameAuthorityResolution(
            decision=AuthorityDecision.SELECTED,
            preferred_name=winner.name,
            confidence=confidence,
            research_context=request.research_context,
            candidates=tuple(ordered),
            retained_names=retained_names,
            explanation=(
                f"“{winner.name}”具有当前候选中最高等级的已审核来源"
                f"（{winner.best_source_level.value if winner.best_source_level else '无'}级，"
                f"{winner.reviewed_document_count} 个独立文献），因此作为当前语境的首选名称；"
                "其他名称仍作为历史异名保留。"
            ),
            requires_human_review=False,
        )

    async def _assess(self, variant: NameVariantInput) -> NameAuthorityCandidate:
        records: list[EvidenceRecord] = []
        missing: list[str] = []
        for evidence_id in variant.evidence_ids:
            record = await self._evidence_repository.get_evidence(evidence_id)
            if record is None:
                missing.append(evidence_id)
            else:
                records.append(record)

        evidence = tuple(self._evidence_view(record) for record in records)
        reviewed = [record for record in records if record.evidence.review_status is ReviewStatus.REVIEWED and record.chunk.review_status is ReviewStatus.REVIEWED]
        levels = [record.evidence.source_level for record in reviewed]
        best_level = min(levels, key=list(SourceLevel).index) if levels else None
        documents = {record.document.id for record in reviewed}
        corroboration_bonus = min(12.0, max(0, len(documents) - 1) * 4.0)
        score = min(100.0, (_AUTHORITY_SCORE[best_level] if best_level else 0.0) + corroboration_bonus)
        reasons = []
        if best_level is not None:
            reasons.append(f"best_source_level_{best_level.value}")
        if len(documents) > 1:
            reasons.append(f"independent_reviewed_documents_{len(documents)}")
        if any(record.evidence.review_status is ReviewStatus.DISPUTED for record in records):
            reasons.append("contains_disputed_evidence")
        if any(record.evidence.review_status is ReviewStatus.PENDING for record in records):
            reasons.append("contains_pending_evidence")
        if missing:
            reasons.append("missing_evidence")
        if not reviewed:
            reasons.append("no_reviewed_evidence")
        return NameAuthorityCandidate(
            name=variant.name,
            score=score,
            eligible=bool(reviewed),
            best_source_level=best_level,
            reviewed_document_count=len(documents),
            evidence=evidence,
            missing_evidence_ids=tuple(missing),
            reasons=tuple(reasons),
        )

    @staticmethod
    def _evidence_view(record: EvidenceRecord) -> AuthorityEvidence:
        contributes = record.evidence.review_status is ReviewStatus.REVIEWED and record.chunk.review_status is ReviewStatus.REVIEWED
        return AuthorityEvidence(
            evidence_id=record.evidence.id,
            document_id=record.document.id,
            document_title=record.document.title,
            edition=record.document.edition,
            source_level=record.evidence.source_level,
            review_status=record.evidence.review_status,
            page_start=record.chunk.page_start,
            page_end=record.chunk.page_end,
            contributes_to_score=contributes,
        )
