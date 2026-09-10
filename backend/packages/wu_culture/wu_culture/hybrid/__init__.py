"""Deterministic lexical/vector retrieval fusion."""

from .service import (
    HybridChannel,
    HybridChannelReport,
    HybridChannelStatus,
    HybridRankingComponents,
    HybridRankingExplanation,
    HybridSearchHit,
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchService,
    HybridSearchUnavailable,
    TemporalMatch,
    classify_hybrid_evidence,
    fuse_rrf,
)

__all__ = [
    "HybridChannel",
    "HybridChannelReport",
    "HybridChannelStatus",
    "HybridSearchHit",
    "HybridSearchRequest",
    "HybridSearchResponse",
    "HybridSearchService",
    "HybridSearchUnavailable",
    "HybridRankingComponents",
    "HybridRankingExplanation",
    "TemporalMatch",
    "classify_hybrid_evidence",
    "fuse_rrf",
]
