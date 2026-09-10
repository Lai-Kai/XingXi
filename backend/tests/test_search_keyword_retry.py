from __future__ import annotations

from types import SimpleNamespace

import pytest
from wu_culture import Citation, EvidenceSearchService, InMemoryEvidenceRepository, ReviewStatus, SourceLevel
from wu_culture.filters import StructuredSearchFilters
from wu_culture.fulltext import FullTextSearchHit, FullTextSearchResponse
from wu_culture.hybrid import HybridSearchUnavailable

from deerflow.agents.xingxi.tools import build_search_sources_tool


class KeywordRepository:
    """An exact keyword channel; the fixture contains no question wording."""

    def __init__(self, *, always_empty=False, extra_text=""):
        self.requests = []
        self.always_empty = always_empty
        self.extra_text = extra_text

    async def resolve_release_id(self, release_id):
        return release_id or "release-1"

    async def search(self, request):
        self.requests.append(request)
        quote = "测试原文：或曰晋陆玩施宅为寺即灵岩寺也。" + self.extra_text
        matches = all(term in quote for term in request.query.split()) and not self.always_empty
        hits = (
            (
                FullTextSearchHit(
                    release_id=request.release_id,
                    chunk_id="chunk-1",
                    score=10,
                    matched_terms=("陆玩", "灵岩寺"),
                    snippet=quote,
                    citation=Citation(
                        evidence_id="fulltext-release-1-chunk-1",
                        document_id="document-1",
                        document_title="测试方志",
                        page_start=1,
                        page_end=1,
                        quote=quote,
                        source_level=SourceLevel.A,
                        review_status=ReviewStatus.REVIEWED,
                    ),
                ),
            )
            if matches
            else ()
        )
        return FullTextSearchResponse(
            query=request.query,
            release_id=request.release_id,
            release_version="v1",
            total=len(hits),
            hits=hits,
            page=1,
            page_size=request.page_size,
        )


class UnavailableStructuredSearch:
    async def search(self, request):
        raise HybridSearchUnavailable("test channel unavailable")


def search_tool(repository, *, direct_fulltext=False):
    return build_search_sources_tool(
        search_service=EvidenceSearchService(InMemoryEvidenceRepository()),
        fulltext_repository=repository,
        structured_search_service=UnavailableStructuredSearch() if direct_fulltext else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("direct_fulltext", [False, True])
async def test_empty_keyword_search_retries_core_terms_with_same_release_and_filters(direct_fulltext):
    repository = KeywordRepository()
    filters = StructuredSearchFilters(document_ids=("document-1",), editions=("测试版",))
    result = await search_tool(repository, direct_fulltext=direct_fulltext).coroutine(
        query="陆玩 灵岩寺 历史联系",
        filters=filters,
        source_levels=["A"],
        top_k=2,
        runtime=SimpleNamespace(context={"knowledge_release_id": "release-1", "knowledge_release_scope": "internal"}),
    )

    assert [request.query for request in repository.requests] == ["陆玩 灵岩寺 历史联系", "陆玩 灵岩寺"]
    assert all(request.release_id == "release-1" for request in repository.requests)
    assert all((request.document_ids or request.filters.document_ids) == ("document-1",) for request in repository.requests)
    assert all(request.filters.editions == ("测试版",) for request in repository.requests)
    assert all((request.source_levels or request.filters.source_levels) == (SourceLevel.A,) for request in repository.requests)
    assert all(request.authorized_use.value == "internal_processing" for request in repository.requests)
    assert result["query"] == "陆玩 灵岩寺 历史联系"
    assert result["resolved_query"] == "陆玩 灵岩寺"
    assert result["evidence_pack"]["items"][0]["evidence_id"] == "fulltext-release-1-chunk-1"


@pytest.mark.asyncio
async def test_successful_original_query_does_not_retry():
    repository = KeywordRepository(extra_text="历史联系")
    result = await search_tool(repository).coroutine(query="陆玩 灵岩寺 历史联系")

    assert [request.query for request in repository.requests] == ["陆玩 灵岩寺 历史联系"]
    assert result["evidence_pack"]["items"]


@pytest.mark.asyncio
async def test_retry_stops_after_one_empty_core_query():
    repository = KeywordRepository(always_empty=True)
    result = await search_tool(repository).coroutine(query="陆玩 灵岩寺 历史联系")

    assert [request.query for request in repository.requests] == ["陆玩 灵岩寺 历史联系", "陆玩 灵岩寺"]
    assert all(request.release_id == "release-1" for request in repository.requests)
    assert result["evidence_pack"]["status"] == "empty"


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ['陆玩 灵岩寺 "历史联系"', "陆玩 灵岩寺 嘉靖", "历史联系", "陆玩 历史联系", "陆玩 灵岩寺"])
async def test_literal_terms_and_successful_queries_do_not_retry(query):
    repository = KeywordRepository()
    await search_tool(repository).coroutine(query=query)

    assert [request.query for request in repository.requests] == [query]
