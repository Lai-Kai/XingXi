from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.hybrid import (
    HybridRankingComponents,
    HybridRankingExplanation,
    HybridSearchHit,
    TemporalMatch,
)
from wu_culture.models import ReviewStatus, SourceLevel

_AUTHORITY = {
    SourceLevel.A: 1.0,
    SourceLevel.B: 0.8,
    SourceLevel.C: 0.6,
    SourceLevel.D: 0.3,
    SourceLevel.E: 0.1,
    SourceLevel.U: 0.0,
}
_REVIEW = {
    ReviewStatus.REVIEWED: 1.0,
    ReviewStatus.DISPUTED: 0.2,
    ReviewStatus.PENDING: 0.0,
    ReviewStatus.REJECTED: 0.0,
}
_TEMPORAL = {
    TemporalMatch.MATCH: 1.0,
    TemporalMatch.UNKNOWN: 0.5,
    TemporalMatch.CONFLICT: 0.0,
}


class TrustRerankConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str = Field(default="trust-rerank-v1", min_length=1, max_length=128)
    relevance_weight: float = Field(default=0.70, ge=0, le=1)
    authority_weight: float = Field(default=0.15, ge=0, le=1)
    review_weight: float = Field(default=0.10, ge=0, le=1)
    temporal_weight: float = Field(default=0.05, ge=0, le=1)
    document_repeat_penalty: float = Field(default=0.05, ge=0, le=1)

    @model_validator(mode="after")
    def validate_weights(self) -> TrustRerankConfig:
        total = self.relevance_weight + self.authority_weight + self.review_weight + self.temporal_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError("trust rerank component weights must sum to 1")
        return self


class TrustReranker:
    """Apply transparent trust signals after retrieval relevance fusion."""

    def __init__(self, config: TrustRerankConfig) -> None:
        self.config = config

    def rerank(
        self,
        hits: tuple[HybridSearchHit, ...],
        *,
        temporal_signals: dict[str, TemporalMatch] | None = None,
    ) -> tuple[HybridSearchHit, ...]:
        if not hits:
            return ()
        signals = temporal_signals or {}
        maximum_relevance = max(hit.fused_score for hit in hits)
        remaining = [
            self._base_candidate(
                hit,
                original_index=index,
                maximum_relevance=maximum_relevance,
                temporal_match=signals.get(hit.chunk_id, TemporalMatch.UNKNOWN),
            )
            for index, hit in enumerate(hits)
        ]
        selected: list[HybridSearchHit] = []
        document_counts: dict[str, int] = {}
        while remaining:
            for candidate in remaining:
                repeats = document_counts.get(candidate["hit"].citation.document_id, 0)
                candidate["diversity_penalty"] = self.config.document_repeat_penalty * repeats
                candidate["final_score"] = candidate["base_score"] - candidate["diversity_penalty"]
            winner = min(
                remaining,
                key=lambda candidate: (
                    -candidate["final_score"],
                    -candidate["base_score"],
                    candidate["original_index"],
                    candidate["hit"].chunk_id,
                ),
            )
            remaining.remove(winner)
            hit = winner["hit"]
            document_counts[hit.citation.document_id] = document_counts.get(hit.citation.document_id, 0) + 1
            reasons = list(winner["reasons"])
            if winner["diversity_penalty"]:
                reasons.append("repeated_document_penalty")
            selected.append(
                hit.model_copy(
                    update={
                        "ranking": HybridRankingExplanation(
                            policy_version=self.config.policy_version,
                            final_score=round(winner["final_score"], 9),
                            temporal_match=winner["temporal_match"],
                            components=HybridRankingComponents(
                                relevance=round(winner["relevance"], 9),
                                authority=round(winner["authority"], 9),
                                review=round(winner["review"], 9),
                                temporal=round(winner["temporal"], 9),
                                diversity_penalty=round(winner["diversity_penalty"], 9),
                            ),
                            reasons=tuple(reasons),
                            warnings=winner["warnings"],
                        )
                    }
                )
            )
        return tuple(selected)

    def _base_candidate(
        self,
        hit: HybridSearchHit,
        *,
        original_index: int,
        maximum_relevance: float,
        temporal_match: TemporalMatch,
    ) -> dict:
        relevance = self.config.relevance_weight * (hit.fused_score / maximum_relevance)
        authority = self.config.authority_weight * _AUTHORITY[hit.citation.source_level]
        review = self.config.review_weight * _REVIEW[hit.citation.review_status]
        temporal = self.config.temporal_weight * _TEMPORAL[temporal_match]
        reasons = (
            "retrieval_relevance",
            f"source_level_{hit.citation.source_level.value}",
            f"review_{hit.citation.review_status.value}",
            f"temporal_{temporal_match.value}",
        )
        warnings = []
        if hit.citation.source_level in {SourceLevel.D, SourceLevel.E, SourceLevel.U}:
            warnings.append("low_authority_source")
        if hit.citation.review_status is ReviewStatus.DISPUTED:
            warnings.append("disputed_review")
        elif hit.citation.review_status is ReviewStatus.PENDING:
            warnings.append("pending_review")
        elif hit.citation.review_status is ReviewStatus.REJECTED:
            warnings.append("rejected_review")
        if temporal_match is TemporalMatch.CONFLICT:
            warnings.append("temporal_conflict")
        return {
            "hit": hit,
            "original_index": original_index,
            "temporal_match": temporal_match,
            "relevance": relevance,
            "authority": authority,
            "review": review,
            "temporal": temporal,
            "base_score": relevance + authority + review + temporal,
            "reasons": reasons,
            "warnings": tuple(warnings),
        }
