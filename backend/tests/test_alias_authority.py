from __future__ import annotations

import pytest
from wu_culture.aliases import AuthorityDecision, NameAuthorityRequest, NameAuthorityService, NameVariantInput
from wu_culture.models import (
    CopyrightStatus,
    Evidence,
    EvidenceRecord,
    ReviewStatus,
    SourceDocument,
    SourceLevel,
    SourceType,
    TextChunk,
)


def _record(
    evidence_id: str,
    *,
    document_id: str,
    title: str,
    level: SourceLevel,
    review_status: ReviewStatus = ReviewStatus.REVIEWED,
) -> EvidenceRecord:
    return EvidenceRecord(
        document=SourceDocument(
            id=document_id,
            title=title,
            source_type=SourceType.GAZETTEER,
            source_level=level,
            copyright_status=CopyrightStatus.PUBLIC_DOMAIN,
        ),
        chunk=TextChunk(
            id=f"chunk-{evidence_id}",
            document_id=document_id,
            original_text="原文",
            normalized_text="原文",
            page_start=12,
            page_end=12,
            review_status=ReviewStatus.REVIEWED,
        ),
        evidence=Evidence(
            id=evidence_id,
            document_id=document_id,
            chunk_id=f"chunk-{evidence_id}",
            quote="原文",
            source_level=level,
            review_status=review_status,
        ),
    )


class _Repository:
    def __init__(self, *records: EvidenceRecord) -> None:
        self.records = {record.evidence.id: record for record in records}

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self.records.get(evidence_id)


@pytest.mark.asyncio
async def test_selects_name_supported_by_higher_authority_reviewed_source() -> None:
    service = NameAuthorityService(
        _Repository(
            _record("ev-a", document_id="doc-a", title="审定方志", level=SourceLevel.A),
            _record("ev-c", document_id="doc-c", title="地方笔记", level=SourceLevel.C),
        )
    )
    result = await service.resolve(
        NameAuthorityRequest(
            variants=(
                NameVariantInput(name="木渎", evidence_ids=("ev-a",)),
                NameVariantInput(name="渎川", evidence_ids=("ev-c",)),
            ),
            research_context="清代镇区地名",
        )
    )

    assert result.decision is AuthorityDecision.SELECTED
    assert result.preferred_name == "木渎"
    assert result.confidence == "high"
    assert result.retained_names == ("木渎", "渎川")
    assert result.requires_human_review is False


@pytest.mark.asyncio
async def test_equal_authority_names_require_human_review() -> None:
    service = NameAuthorityService(
        _Repository(
            _record("ev-1", document_id="doc-1", title="古籍甲", level=SourceLevel.A),
            _record("ev-2", document_id="doc-2", title="古籍乙", level=SourceLevel.A),
        )
    )
    result = await service.resolve(
        NameAuthorityRequest(
            variants=(
                NameVariantInput(name="香溪", evidence_ids=("ev-1",)),
                NameVariantInput(name="胥溪", evidence_ids=("ev-2",)),
            )
        )
    )

    assert result.decision is AuthorityDecision.NEEDS_REVIEW
    assert result.preferred_name is None
    assert result.requires_human_review is True
    assert {candidate.name for candidate in result.candidates} == {"香溪", "胥溪"}


@pytest.mark.asyncio
async def test_pending_or_missing_evidence_cannot_win() -> None:
    service = NameAuthorityService(
        _Repository(
            _record(
                "ev-pending",
                document_id="doc-pending",
                title="待审材料",
                level=SourceLevel.A,
                review_status=ReviewStatus.PENDING,
            )
        )
    )
    result = await service.resolve(
        NameAuthorityRequest(
            variants=(
                NameVariantInput(name="候选甲", evidence_ids=("ev-pending",)),
                NameVariantInput(name="候选乙", evidence_ids=("ev-missing",)),
            )
        )
    )

    assert result.decision is AuthorityDecision.INSUFFICIENT_EVIDENCE
    assert result.preferred_name is None
    assert all(not candidate.eligible for candidate in result.candidates)
