from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from wu_culture import Citation, ReviewStatus, SourceLevel
from wu_culture.filters import Dynasty
from wu_culture.fulltext import FullTextSearchHit, FullTextSearchResponse
from wu_culture.hybrid import (
    HybridChannelStatus,
    HybridSearchRequest,
    HybridSearchService,
    HybridSearchUnavailable,
)
from wu_culture.ranking import TrustRerankConfig, TrustReranker
from wu_culture.vectors import VectorSearchHit, VectorSearchResponse

from deerflow.agents.xingxi.tools import build_compare_sources_tool, build_search_sources_tool


def _citation(chunk_id: str) -> Citation:
    return Citation(
        evidence_id=f"evidence-{chunk_id}",
        document_id="document-1",
        document_title="木渎小志",
        page_start=1,
        page_end=1,
        quote=f"quote {chunk_id}",
        source_level=SourceLevel.A,
        review_status=ReviewStatus.REVIEWED,
    )


class _FullText:
    def __init__(self, hits=(), *, delay=0.0, error=None) -> None:
        self.hits = hits
        self.delay = delay
        self.error = error
        self.request = None

    async def resolve_release_id(self, release_id):
        return release_id or "release-1"

    async def search(self, request):
        self.request = request
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return FullTextSearchResponse(
            query=request.query,
            release_id=request.release_id,
            release_version="v1",
            total=len(self.hits),
            page=1,
            page_size=request.page_size,
            hits=self.hits,
        )


class _Vectors:
    def __init__(self, hits=(), *, delay=0.0, error=None, response_release_id=None) -> None:
        self.hits = hits
        self.delay = delay
        self.error = error
        self.response_release_id = response_release_id
        self.request = None

    async def search(self, request):
        self.request = request
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return VectorSearchResponse(
            query=request.query,
            release_id=self.response_release_id or request.release_id,
            index_id="vector-1",
            embedding_model="embedding-model",
            embedding_version="v1",
            hits=self.hits,
        )


class _UnavailableHybrid:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, request):  # noqa: ANN001
        self.calls += 1
        raise HybridSearchUnavailable("full-text and vector retrieval channels are both unavailable")


def test_rrf_merges_duplicate_chunks_and_exposes_both_channel_scores() -> None:
    asyncio.run(_exercise_rrf_merge())


async def _exercise_rrf_merge() -> None:
    fulltext = _FullText(
        (
            FullTextSearchHit(
                release_id="release-1",
                chunk_id="chunk-shared",
                score=12.0,
                matched_terms=("木渎",),
                snippet="【木渎】旧桥",
                citation=_citation("chunk-shared"),
            ),
            FullTextSearchHit(
                release_id="release-1",
                chunk_id="chunk-lexical",
                score=8.0,
                matched_terms=("木渎",),
                snippet="【木渎】",
                citation=_citation("chunk-lexical"),
            ),
        )
    )
    vectors = _Vectors(
        (
            VectorSearchHit(
                release_id="release-1",
                index_id="vector-1",
                chunk_id="chunk-vector",
                similarity=0.95,
                citation=_citation("chunk-vector"),
            ),
            VectorSearchHit(
                release_id="release-1",
                index_id="vector-1",
                chunk_id="chunk-shared",
                similarity=0.9,
                citation=_citation("chunk-shared"),
            ),
        )
    )
    response = await HybridSearchService(fulltext, vectors, timeout_seconds=1.0, rrf_k=60).search(HybridSearchRequest(query="河岸附近的老桥", top_k=3, candidate_k=10))

    assert response.release_id == "release-1"
    assert response.algorithm == "rrf"
    assert response.degraded is False
    assert [hit.chunk_id for hit in response.hits] == ["chunk-shared", "chunk-vector", "chunk-lexical"]
    shared = response.hits[0]
    assert shared.channels == ("fulltext", "vector")
    assert shared.fulltext_rank == 1
    assert shared.vector_rank == 2
    assert shared.fulltext_score == 12.0
    assert shared.vector_similarity == 0.9
    assert shared.fulltext_rrf_contribution == pytest.approx(1 / 61)
    assert shared.vector_rrf_contribution == pytest.approx(1 / 62)
    assert shared.fused_score == pytest.approx(1 / 61 + 1 / 62)
    assert fulltext.request.release_id == vectors.request.release_id == "release-1"


def test_one_channel_timeout_returns_other_channel_and_marks_degraded() -> None:
    async def exercise() -> None:
        fulltext = _FullText(
            (
                FullTextSearchHit(
                    release_id="release-1",
                    chunk_id="chunk-lexical",
                    score=5.0,
                    matched_terms=("桥",),
                    snippet="【桥】",
                    citation=_citation("chunk-lexical"),
                ),
            )
        )
        vectors = _Vectors(delay=0.05)
        response = await HybridSearchService(fulltext, vectors, timeout_seconds=0.001).search(HybridSearchRequest(query="旧桥"))

        assert [hit.chunk_id for hit in response.hits] == ["chunk-lexical"]
        assert response.degraded is True
        assert response.channel_reports[0].status is HybridChannelStatus.OK
        assert response.channel_reports[1].status is HybridChannelStatus.TIMEOUT

    asyncio.run(exercise())


def test_both_channels_unavailable_raises_instead_of_returning_false_empty() -> None:
    async def exercise() -> None:
        service = HybridSearchService(
            _FullText(error=RuntimeError("fts down")),
            _Vectors(error=RuntimeError("vector down")),
            timeout_seconds=1.0,
        )
        with pytest.raises(HybridSearchUnavailable):
            await service.search(HybridSearchRequest(query="旧桥"))

    asyncio.run(exercise())


def test_search_tool_falls_back_to_direct_fulltext_after_hybrid_timeout() -> None:
    async def exercise() -> None:
        fulltext = _FullText(
            (
                FullTextSearchHit(
                    release_id="release-1",
                    chunk_id="chunk-fulltext-fallback",
                    score=5.0,
                    matched_terms=("木渎镇",),
                    snippet="【木渎镇】",
                    citation=_citation("chunk-fulltext-fallback"),
                ),
            )
        )
        hybrid = _UnavailableHybrid()
        tool = build_search_sources_tool(
            fulltext_repository=fulltext,
            hybrid_search_service=hybrid,
        )
        runtime = SimpleNamespace(
            context={
                "knowledge_release_id": "release-1",
                "knowledge_release_scope": "internal",
            },
            config={},
        )

        result = await tool.coroutine(query="木渎镇", top_k=3, cursor="", runtime=runtime)

        assert result["status"] == "supported"
        assert result["release_id"] == "release-1"
        assert result["evidence_pack"]["items"][0]["evidence_id"] == "evidence-chunk-fulltext-fallback"
        assert hybrid.calls == 1
        assert fulltext.request.authorized_use.value == "internal_processing"

    asyncio.run(exercise())


def test_fulltext_error_returns_vector_only_result() -> None:
    async def exercise() -> None:
        vectors = _Vectors(
            (
                VectorSearchHit(
                    release_id="release-1",
                    index_id="vector-1",
                    chunk_id="chunk-vector",
                    similarity=0.92,
                    citation=_citation("chunk-vector"),
                ),
            )
        )
        response = await HybridSearchService(
            _FullText(error=RuntimeError("fts unavailable")),
            vectors,
            timeout_seconds=1.0,
        ).search(HybridSearchRequest(query="河岸附近的老桥"))

        assert [hit.chunk_id for hit in response.hits] == ["chunk-vector"]
        assert response.hits[0].channels == ("vector",)
        assert response.channel_reports[0].status is HybridChannelStatus.ERROR
        assert response.channel_reports[1].status is HybridChannelStatus.OK
        assert response.degraded is True

    asyncio.run(exercise())


def test_search_sources_tool_returns_fused_channel_observability() -> None:
    async def exercise() -> None:
        fulltext = _FullText(
            (
                FullTextSearchHit(
                    release_id="release-1",
                    chunk_id="chunk-shared",
                    score=5.0,
                    matched_terms=("桥",),
                    snippet="【桥】",
                    citation=_citation("chunk-shared"),
                ),
            )
        )
        vectors = _Vectors(
            (
                VectorSearchHit(
                    release_id="release-1",
                    index_id="vector-1",
                    chunk_id="chunk-shared",
                    similarity=0.9,
                    citation=_citation("chunk-shared"),
                ),
            )
        )
        hybrid = HybridSearchService(fulltext, vectors)
        result = await build_search_sources_tool(hybrid_search_service=hybrid).ainvoke({"query": "河岸附近的老桥", "top_k": 3})

        assert result["status"] == "supported"
        assert len(result["hits"]) == 1
        assert result["hits"][0]["channels"] == ["fulltext", "vector"]
        assert result["hits"][0]["included_in_evidence_pack"] is True
        assert result["evidence_pack"]["schema_version"] == "evidence-pack-v1"
        assert result["evidence_pack"]["status"] == "ready"
        assert result["evidence_pack"]["items"][0]["evidence_id"] == result["hits"][0]["evidence_id"]
        assert result["evidence_pack"]["items"][0]["quote_provenance"] == "verbatim"
        assert result["channels"] == [
            {"channel": "fulltext", "status": "ok", "hit_count": 1, "error_code": None},
            {"channel": "vector", "status": "ok", "hit_count": 1, "error_code": None},
        ]

    asyncio.run(exercise())


def test_compare_sources_tool_uses_hybrid_request_limits() -> None:
    async def exercise() -> None:
        fulltext = _FullText(
            (
                FullTextSearchHit(
                    release_id="release-1",
                    chunk_id="chunk-compare",
                    score=5.0,
                    matched_terms=("桥",),
                    snippet="【桥】",
                    citation=_citation("chunk-compare"),
                ),
            )
        )
        tool = build_compare_sources_tool(hybrid_search_service=HybridSearchService(fulltext, None))

        result = await tool.ainvoke({"topic": "香溪桥"})

        assert result["schema_version"] == "compare-sources-v1"
        assert result["status"] == "single_source"
        assert fulltext.request is not None
        assert fulltext.request.page_size >= 6

    asyncio.run(exercise())


def test_search_sources_tool_uses_same_nested_structured_filter_schema() -> None:
    async def exercise() -> None:
        fulltext = _FullText()
        hybrid = HybridSearchService(fulltext, None)
        result = await build_search_sources_tool(hybrid_search_service=hybrid).ainvoke(
            {
                "query": "旧桥",
                "filters": {
                    "dynasties": ["qing"],
                    "entity_types": ["bridge"],
                },
                "top_k": 3,
            }
        )

        assert result["filters"] == {"dynasties": ["qing"], "entity_types": ["bridge"]}
        assert fulltext.request.filters.dynasties == (Dynasty.QING,)
        assert result["has_more"] is False

    asyncio.run(exercise())


def test_mismatched_release_channel_is_rejected_and_cannot_leak_candidates() -> None:
    async def exercise() -> None:
        fulltext = _FullText()
        vectors = _Vectors(
            (
                VectorSearchHit(
                    release_id="release-other",
                    index_id="vector-other",
                    chunk_id="chunk-other",
                    similarity=0.99,
                    citation=_citation("chunk-other"),
                ),
            ),
            response_release_id="release-other",
        )
        response = await HybridSearchService(fulltext, vectors).search(HybridSearchRequest(query="旧桥"))

        assert response.hits == ()
        assert response.degraded is True
        assert response.channel_reports[1].error_code == "release_mismatch"

    asyncio.run(exercise())


def test_channels_start_concurrently_instead_of_serially() -> None:
    async def exercise() -> None:
        fulltext_started = asyncio.Event()
        vector_started = asyncio.Event()

        class CoordinatedFullText(_FullText):
            async def search(self, request):
                fulltext_started.set()
                await vector_started.wait()
                return await super().search(request)

        class CoordinatedVectors(_Vectors):
            async def search(self, request):
                vector_started.set()
                await fulltext_started.wait()
                return await super().search(request)

        response = await HybridSearchService(
            CoordinatedFullText(),
            CoordinatedVectors(),
            timeout_seconds=0.5,
        ).search(HybridSearchRequest(query="旧桥"))

        assert [report.status for report in response.channel_reports] == [
            HybridChannelStatus.EMPTY,
            HybridChannelStatus.EMPTY,
        ]
        assert response.degraded is False

    asyncio.run(exercise())


def test_hybrid_service_applies_configured_trust_reranker_after_rrf() -> None:
    async def exercise() -> None:
        fulltext = _FullText(
            (
                FullTextSearchHit(
                    release_id="release-1",
                    chunk_id="low",
                    score=10.0,
                    matched_terms=("桥",),
                    snippet="【桥】",
                    citation=_citation("low").model_copy(update={"source_level": SourceLevel.D}),
                ),
                FullTextSearchHit(
                    release_id="release-1",
                    chunk_id="authority",
                    score=9.0,
                    matched_terms=("桥",),
                    snippet="【桥】",
                    citation=_citation("authority"),
                ),
            )
        )
        response = await HybridSearchService(
            fulltext,
            None,
            reranker=TrustReranker(TrustRerankConfig()),
        ).search(HybridSearchRequest(query="旧桥", top_k=2))

        assert response.ranking_applied is True
        assert [hit.chunk_id for hit in response.hits] == ["authority", "low"]
        assert response.hits[0].ranking.policy_version == "trust-rerank-v1"

    asyncio.run(exercise())


def test_low_grade_and_disputed_results_keep_explicit_evidence_status() -> None:
    async def exercise() -> None:
        low = _FullText(
            (
                FullTextSearchHit(
                    release_id="release-1",
                    chunk_id="low",
                    score=10.0,
                    matched_terms=("桥",),
                    snippet="【桥】",
                    citation=_citation("low").model_copy(update={"source_level": SourceLevel.E}),
                ),
            )
        )
        low_response = await HybridSearchService(low, None).search(HybridSearchRequest(query="旧桥"))
        assert low_response.evidence_status.value == "inferred"

        disputed = _FullText(
            (
                FullTextSearchHit(
                    release_id="release-1",
                    chunk_id="disputed",
                    score=10.0,
                    matched_terms=("桥",),
                    snippet="【桥】",
                    citation=_citation("disputed").model_copy(update={"review_status": ReviewStatus.DISPUTED}),
                ),
            )
        )
        disputed_response = await HybridSearchService(disputed, None).search(HybridSearchRequest(query="旧桥"))
        assert disputed_response.evidence_status.value == "conflicting"

    asyncio.run(exercise())


def test_reranking_uses_candidate_pool_before_top_k_truncation() -> None:
    async def exercise() -> None:
        hits = tuple(
            FullTextSearchHit(
                release_id="release-1",
                chunk_id=chunk_id,
                score=10.0 - index,
                matched_terms=("桥",),
                snippet="【桥】",
                citation=_citation(chunk_id).model_copy(update={"document_id": document_id}),
            )
            for index, (chunk_id, document_id) in enumerate(
                (
                    ("same-1", "document-same"),
                    ("same-2", "document-same"),
                    ("other", "document-other"),
                )
            )
        )
        response = await HybridSearchService(
            _FullText(hits),
            None,
            reranker=TrustReranker(TrustRerankConfig(document_repeat_penalty=0.08)),
        ).search(HybridSearchRequest(query="旧桥", top_k=2, candidate_k=3))

        assert [hit.chunk_id for hit in response.hits] == ["same-1", "other"]

    asyncio.run(exercise())
