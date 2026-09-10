from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.evidence_pack import EvidencePack, EvidencePackAssembler
from wu_culture.filters import StructuredSearchFilters
from wu_culture.fulltext import FullTextRepository, FullTextSearchRequest, FullTextSearchResponse
from wu_culture.models import AuthorizedUse, Citation, ReviewStatus, SearchStatus, SourceLevel, SourceType
from wu_culture.vectors import VectorSearchRequest, VectorSearchResponse

logger = logging.getLogger(__name__)


class HybridSearchUnavailable(RuntimeError):
    """Raised when neither retrieval channel can provide a valid response."""


class HybridChannel(StrEnum):
    FULLTEXT = "fulltext"
    VECTOR = "vector"


class HybridChannelStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class TemporalMatch(StrEnum):
    MATCH = "match"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class _HybridModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class HybridSearchRequest(_HybridModel):
    query: str = Field(min_length=1, max_length=500)
    release_id: str | None = Field(default=None, min_length=1, max_length=255)
    document_ids: tuple[str, ...] | None = Field(default=None, max_length=100)
    source_levels: tuple[SourceLevel, ...] | None = None
    source_types: tuple[SourceType, ...] | None = None
    authorized_use: AuthorizedUse = AuthorizedUse.PUBLIC_QUOTE
    filters: StructuredSearchFilters = Field(default_factory=StructuredSearchFilters)
    top_k: int = Field(default=10, ge=1, le=100)
    candidate_k: int = Field(default=30, ge=1, le=100)
    min_vector_similarity: float = Field(default=0.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_request(self) -> HybridSearchRequest:
        if self.document_ids and len(self.document_ids) != len(set(self.document_ids)):
            raise ValueError("duplicate document filter")
        if self.candidate_k < self.top_k:
            raise ValueError("candidate_k must be greater than or equal to top_k")
        return self


class HybridChannelReport(_HybridModel):
    channel: HybridChannel
    status: HybridChannelStatus
    hit_count: int = Field(default=0, ge=0)
    error_code: str | None = None


class HybridRankingComponents(_HybridModel):
    relevance: float = Field(ge=0)
    authority: float = Field(ge=0)
    review: float = Field(ge=0)
    temporal: float = Field(ge=0)
    diversity_penalty: float = Field(ge=0)


class HybridRankingExplanation(_HybridModel):
    policy_version: str
    final_score: float
    temporal_match: TemporalMatch
    components: HybridRankingComponents
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


class HybridSearchHit(_HybridModel):
    release_id: str
    chunk_id: str
    fused_score: float = Field(gt=0)
    channels: tuple[HybridChannel, ...]
    fulltext_rank: int | None = Field(default=None, ge=1)
    fulltext_score: float | None = Field(default=None, ge=0)
    fulltext_rrf_contribution: float | None = Field(default=None, gt=0)
    vector_rank: int | None = Field(default=None, ge=1)
    vector_similarity: float | None = Field(default=None, ge=-1, le=1)
    vector_rrf_contribution: float | None = Field(default=None, gt=0)
    citation: Citation
    ranking: HybridRankingExplanation | None = None


class HybridSearchResponse(_HybridModel):
    query: str
    release_id: str
    algorithm: str = "rrf"
    rrf_k: int = Field(ge=1)
    degraded: bool
    ranking_applied: bool = False
    channel_reports: tuple[HybridChannelReport, ...]
    hits: tuple[HybridSearchHit, ...]
    evidence_status: SearchStatus
    message: str
    confidence_notice: str = "融合与重排分数仅表示候选优先级，不代表事实可信度"
    evidence_pack: EvidencePack | None = None


class VectorSearchService(Protocol):
    async def search(self, request: VectorSearchRequest) -> VectorSearchResponse: ...


class HybridReranker(Protocol):
    def rerank(
        self,
        hits: tuple[HybridSearchHit, ...],
        *,
        temporal_signals: dict[str, TemporalMatch] | None = None,
    ) -> tuple[HybridSearchHit, ...]: ...


class HybridSearchService:
    """Run lexical and semantic retrieval concurrently and fuse by Chunk ID."""

    def __init__(
        self,
        fulltext: FullTextRepository,
        vectors: VectorSearchService | None,
        *,
        timeout_seconds: float = 5.0,
        rrf_k: int = 60,
        reranker: HybridReranker | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("hybrid channel timeout must be positive")
        if rrf_k < 1:
            raise ValueError("rrf_k must be at least 1")
        self._fulltext = fulltext
        self._vectors = vectors
        self._timeout_seconds = timeout_seconds
        self._rrf_k = rrf_k
        self._reranker = reranker

    async def search(
        self,
        request: HybridSearchRequest,
        *,
        temporal_signals: dict[str, TemporalMatch] | None = None,
    ) -> HybridSearchResponse:
        release_id = await self._fulltext.resolve_release_id(request.release_id)
        fulltext_request = FullTextSearchRequest(
            query=request.query,
            release_id=release_id,
            document_ids=request.document_ids,
            source_levels=request.source_levels,
            source_types=request.source_types,
            authorized_use=request.authorized_use,
            filters=request.filters,
            page_size=request.candidate_k,
        )
        vector_request = VectorSearchRequest(
            query=request.query,
            release_id=release_id,
            document_ids=request.document_ids,
            source_levels=request.source_levels,
            source_types=request.source_types,
            authorized_use=request.authorized_use,
            filters=request.filters,
            top_k=request.candidate_k,
            min_similarity=request.min_vector_similarity,
        )

        fulltext_task = asyncio.create_task(self._call_channel(HybridChannel.FULLTEXT, self._fulltext.search(fulltext_request)))
        if self._vectors is None:
            vector_task = asyncio.create_task(self._unavailable_vector())
        else:
            vector_task = asyncio.create_task(self._call_channel(HybridChannel.VECTOR, self._vectors.search(vector_request)))
        (fulltext_response, fulltext_report), (vector_response, vector_report) = await asyncio.gather(
            fulltext_task,
            vector_task,
        )
        fulltext_response, fulltext_report = self._require_release(
            release_id,
            fulltext_response,
            fulltext_report,
        )
        vector_response, vector_report = self._require_release(
            release_id,
            vector_response,
            vector_report,
        )

        usable = {HybridChannelStatus.OK, HybridChannelStatus.EMPTY}
        if fulltext_report.status not in usable and vector_report.status not in usable:
            raise HybridSearchUnavailable("full-text and vector retrieval channels are both unavailable")
        hits = fuse_rrf(
            fulltext_response if isinstance(fulltext_response, FullTextSearchResponse) else None,
            vector_response if isinstance(vector_response, VectorSearchResponse) else None,
            rrf_k=self._rrf_k,
            top_k=request.candidate_k if self._reranker is not None else request.top_k,
        )
        if self._reranker is not None:
            hits = self._reranker.rerank(hits, temporal_signals=temporal_signals)[: request.top_k]
        degraded = any(report.status in {HybridChannelStatus.TIMEOUT, HybridChannelStatus.ERROR, HybridChannelStatus.UNAVAILABLE} for report in (fulltext_report, vector_report))
        evidence_status, message = classify_hybrid_evidence(hits)
        evidence_pack = EvidencePackAssembler().assemble(hits, release_id=release_id)
        return HybridSearchResponse(
            query=request.query,
            release_id=release_id,
            rrf_k=self._rrf_k,
            degraded=degraded,
            ranking_applied=self._reranker is not None,
            channel_reports=(fulltext_report, vector_report),
            hits=hits,
            evidence_status=evidence_status,
            message=message,
            evidence_pack=evidence_pack,
        )

    async def _call_channel(self, channel: HybridChannel, operation):  # noqa: ANN001, ANN202
        try:
            response = await asyncio.wait_for(operation, timeout=self._timeout_seconds)
            hit_count = len(response.hits)
            status = HybridChannelStatus.OK if hit_count else HybridChannelStatus.EMPTY
            return response, HybridChannelReport(channel=channel, status=status, hit_count=hit_count)
        except TimeoutError:
            return None, HybridChannelReport(channel=channel, status=HybridChannelStatus.TIMEOUT, error_code="timeout")
        except Exception as exc:
            logger.warning("Hybrid %s channel failed: %s", channel.value, type(exc).__name__)
            return None, HybridChannelReport(
                channel=channel,
                status=HybridChannelStatus.ERROR,
                error_code=type(exc).__name__,
            )

    @staticmethod
    async def _unavailable_vector():  # noqa: ANN205
        return None, HybridChannelReport(
            channel=HybridChannel.VECTOR,
            status=HybridChannelStatus.UNAVAILABLE,
            error_code="embedding_disabled",
        )

    @staticmethod
    def _require_release(release_id: str, response, report: HybridChannelReport):  # noqa: ANN001, ANN205
        if response is None or response.release_id == release_id:
            return response, report
        logger.error(
            "Hybrid %s channel returned a mismatched release",
            report.channel.value,
        )
        return None, HybridChannelReport(
            channel=report.channel,
            status=HybridChannelStatus.ERROR,
            error_code="release_mismatch",
        )


def fuse_rrf(
    fulltext: FullTextSearchResponse | None,
    vectors: VectorSearchResponse | None,
    *,
    rrf_k: int,
    top_k: int,
) -> tuple[HybridSearchHit, ...]:
    candidates: dict[str, dict] = {}
    for rank, hit in enumerate(fulltext.hits if fulltext is not None else (), start=1):
        candidate = candidates.setdefault(
            hit.chunk_id,
            {"release_id": hit.release_id, "chunk_id": hit.chunk_id, "score": 0.0, "citation": hit.citation},
        )
        contribution = 1.0 / (rrf_k + rank)
        candidate.update(
            fulltext_rank=rank,
            fulltext_score=hit.score,
            fulltext_rrf_contribution=contribution,
            citation=hit.citation,
        )
        candidate["score"] += contribution
    for rank, hit in enumerate(vectors.hits if vectors is not None else (), start=1):
        candidate = candidates.setdefault(
            hit.chunk_id,
            {"release_id": hit.release_id, "chunk_id": hit.chunk_id, "score": 0.0, "citation": hit.citation},
        )
        contribution = 1.0 / (rrf_k + rank)
        candidate.update(
            vector_rank=rank,
            vector_similarity=hit.similarity,
            vector_rrf_contribution=contribution,
        )
        candidate["score"] += contribution

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            -item["score"],
            min(item.get("fulltext_rank", 10**9), item.get("vector_rank", 10**9)),
            item["chunk_id"],
        ),
    )
    results = []
    for item in ordered[:top_k]:
        channels = tuple(
            channel
            for channel, rank_key in (
                (HybridChannel.FULLTEXT, "fulltext_rank"),
                (HybridChannel.VECTOR, "vector_rank"),
            )
            if rank_key in item
        )
        results.append(
            HybridSearchHit(
                release_id=item["release_id"],
                chunk_id=item["chunk_id"],
                fused_score=item["score"],
                channels=channels,
                fulltext_rank=item.get("fulltext_rank"),
                fulltext_score=item.get("fulltext_score"),
                fulltext_rrf_contribution=item.get("fulltext_rrf_contribution"),
                vector_rank=item.get("vector_rank"),
                vector_similarity=item.get("vector_similarity"),
                vector_rrf_contribution=item.get("vector_rrf_contribution"),
                citation=item["citation"],
            )
        )
    return tuple(results)


def classify_hybrid_evidence(hits: tuple[HybridSearchHit, ...]) -> tuple[SearchStatus, str]:
    if not hits:
        return SearchStatus.INSUFFICIENT, "暂无明确方志记载"
    if any(hit.citation.review_status is ReviewStatus.DISPUTED for hit in hits):
        return SearchStatus.CONFLICTING, "检索到存在争议的证据，请并列呈现不同记载"
    if all(hit.citation.source_level in {SourceLevel.D, SourceLevel.E, SourceLevel.U} for hit in hits):
        return SearchStatus.INFERRED, "仅检索到低等级来源或推测，不得表述为确定史实"
    return SearchStatus.SUPPORTED, "已检索到可引用证据"
