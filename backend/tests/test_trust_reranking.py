from __future__ import annotations

import pytest
from pydantic import ValidationError
from wu_culture import Citation, ReviewStatus, SourceLevel
from wu_culture.hybrid import HybridChannel, HybridSearchHit
from wu_culture.ranking import TemporalMatch, TrustRerankConfig, TrustReranker


def _hit(
    chunk_id: str,
    *,
    fused_score: float,
    level: SourceLevel,
    review: ReviewStatus = ReviewStatus.REVIEWED,
    document_id: str | None = None,
) -> HybridSearchHit:
    return HybridSearchHit(
        release_id="release-1",
        chunk_id=chunk_id,
        fused_score=fused_score,
        channels=(HybridChannel.FULLTEXT,),
        fulltext_rank=1,
        fulltext_score=10.0,
        fulltext_rrf_contribution=fused_score,
        citation=Citation(
            evidence_id=f"evidence-{chunk_id}",
            document_id=document_id or f"document-{chunk_id}",
            document_title=f"文献 {chunk_id}",
            page_start=1,
            page_end=1,
            quote=f"原文 {chunk_id}",
            source_level=level,
            review_status=review,
        ),
    )


def test_authoritative_slightly_lower_relevance_outranks_low_grade_but_strong_low_grade_survives() -> None:
    reranker = TrustReranker(TrustRerankConfig())
    close = reranker.rerank(
        (
            _hit("low-close", fused_score=1.0, level=SourceLevel.D),
            _hit("authoritative-close", fused_score=0.95, level=SourceLevel.A),
        )
    )

    assert [hit.chunk_id for hit in close] == ["authoritative-close", "low-close"]
    assert close[1].ranking is not None
    assert "low_authority_source" in close[1].ranking.warnings

    strong = reranker.rerank(
        (
            _hit("low-strong", fused_score=1.0, level=SourceLevel.D),
            _hit("authoritative-weak", fused_score=0.4, level=SourceLevel.A),
        )
    )
    assert [hit.chunk_id for hit in strong] == ["low-strong", "authoritative-weak"]


def test_disputed_evidence_is_retained_penalized_and_explained() -> None:
    ranked = TrustReranker(TrustRerankConfig()).rerank(
        (
            _hit("disputed", fused_score=1.0, level=SourceLevel.A, review=ReviewStatus.DISPUTED),
            _hit("reviewed", fused_score=0.95, level=SourceLevel.A),
        )
    )

    assert [hit.chunk_id for hit in ranked] == ["reviewed", "disputed"]
    assert "disputed_review" in ranked[1].ranking.warnings
    assert ranked[1].ranking.components.review < ranked[0].ranking.components.review


def test_verified_temporal_signal_contributes_but_unknown_does_not_invent_a_match() -> None:
    ranked = TrustReranker(TrustRerankConfig()).rerank(
        (
            _hit("unknown", fused_score=1.0, level=SourceLevel.B),
            _hit("matching", fused_score=1.0, level=SourceLevel.B),
            _hit("conflicting", fused_score=1.0, level=SourceLevel.B),
        ),
        temporal_signals={
            "matching": TemporalMatch.MATCH,
            "conflicting": TemporalMatch.CONFLICT,
        },
    )

    assert [hit.chunk_id for hit in ranked] == ["matching", "unknown", "conflicting"]
    assert ranked[1].ranking.temporal_match is TemporalMatch.UNKNOWN
    assert "temporal_conflict" in ranked[2].ranking.warnings


def test_document_diversity_penalty_prevents_one_source_from_filling_top_results() -> None:
    config = TrustRerankConfig(document_repeat_penalty=0.08)
    ranked = TrustReranker(config).rerank(
        (
            _hit("same-1", fused_score=1.0, level=SourceLevel.A, document_id="document-same"),
            _hit("same-2", fused_score=0.99, level=SourceLevel.A, document_id="document-same"),
            _hit("other", fused_score=0.94, level=SourceLevel.A, document_id="document-other"),
        )
    )

    assert [hit.chunk_id for hit in ranked] == ["same-1", "other", "same-2"]
    assert ranked[2].ranking.components.diversity_penalty == 0.08
    assert "repeated_document_penalty" in ranked[2].ranking.reasons


def test_rerank_component_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match="sum to 1"):
        TrustRerankConfig(relevance_weight=0.5)


def test_config_can_prioritize_pure_relevance_without_hidden_weights() -> None:
    ranked = TrustReranker(
        TrustRerankConfig(
            relevance_weight=1.0,
            authority_weight=0.0,
            review_weight=0.0,
            temporal_weight=0.0,
        )
    ).rerank(
        (
            _hit("low", fused_score=1.0, level=SourceLevel.D),
            _hit("authority", fused_score=0.95, level=SourceLevel.A),
        )
    )

    assert [hit.chunk_id for hit in ranked] == ["low", "authority"]
    assert ranked[0].ranking.components.authority == 0.0
