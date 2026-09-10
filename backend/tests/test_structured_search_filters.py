from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from wu_culture import Citation, EntityType, ReviewStatus, SearchStatus, SourceLevel, SourceType
from wu_culture.filters import Dynasty, StructuredSearchFilters
from wu_culture.hybrid import HybridChannel, HybridChannelReport, HybridChannelStatus, HybridSearchHit, HybridSearchResponse
from wu_culture.structured_search import (
    StructuredSearchCursorError,
    StructuredSearchRequest,
    StructuredSearchService,
    decode_search_cursor,
    encode_search_cursor,
)


def test_filter_schema_is_typed_deduplicated_and_forbids_unknown_fields() -> None:
    filters = StructuredSearchFilters(
        document_ids=("document-1",),
        editions=("清同治本",),
        source_types=(SourceType.GAZETTEER,),
        source_levels=(SourceLevel.A,),
        dynasties=(Dynasty.QING,),
        entity_types=(EntityType.BRIDGE,),
        review_statuses=(ReviewStatus.REVIEWED,),
        min_spatial_confidence=0.7,
        max_spatial_confidence=0.95,
    )

    assert filters.dynasties == (Dynasty.QING,)
    assert filters.entity_types == (EntityType.BRIDGE,)
    with pytest.raises(ValidationError, match="duplicate document_ids"):
        StructuredSearchFilters(document_ids=("document-1", "document-1"))
    with pytest.raises(ValidationError):
        StructuredSearchFilters(dynasties=("not-a-dynasty",))
    with pytest.raises(ValidationError):
        StructuredSearchFilters(undeclared_sql="DROP TABLE")
    with pytest.raises(ValidationError, match="maximum spatial confidence"):
        StructuredSearchFilters(min_spatial_confidence=0.9, max_spatial_confidence=0.2)


def test_cursor_is_bound_to_release_and_request_fingerprint() -> None:
    request = StructuredSearchRequest(
        query="木渎古桥",
        filters=StructuredSearchFilters(dynasties=(Dynasty.QING,)),
        page_size=20,
        candidate_k=100,
    )
    cursor = encode_search_cursor(
        release_id="release-1",
        request_fingerprint=request.fingerprint,
        offset=40,
    )
    payload = decode_search_cursor(cursor)

    assert payload.release_id == "release-1"
    assert payload.request_fingerprint == request.fingerprint
    assert payload.offset == 40
    changed = request.model_copy(update={"filters": StructuredSearchFilters(dynasties=(Dynasty.MING,))})
    assert changed.fingerprint != request.fingerprint
    with pytest.raises(StructuredSearchCursorError):
        decode_search_cursor("not-base64-json")


def test_request_rejects_cursor_like_free_form_filters_and_unbounded_pages() -> None:
    with pytest.raises(ValidationError):
        StructuredSearchRequest(query="古桥", page_size=51)
    with pytest.raises(ValidationError):
        StructuredSearchRequest(query="古桥", candidate_k=101)


def test_cursor_pages_large_ranked_candidate_set_without_duplicates() -> None:
    asyncio.run(_exercise_cursor_pages())


async def _exercise_cursor_pages() -> None:
    class FakeHybrid:
        async def search(self, request):
            hits = tuple(
                HybridSearchHit(
                    release_id="release-1",
                    chunk_id=f"chunk-{index:03d}",
                    fused_score=1.0 / (index + 1),
                    channels=(HybridChannel.FULLTEXT,),
                    fulltext_rank=index + 1,
                    fulltext_score=float(100 - index),
                    fulltext_rrf_contribution=1.0 / (index + 1),
                    citation=Citation(
                        evidence_id=f"evidence-{index:03d}",
                        document_id=f"document-{index:03d}",
                        document_title="测试文献",
                        page_start=1,
                        page_end=1,
                        quote="测试原文",
                        source_level=SourceLevel.A,
                        review_status=ReviewStatus.REVIEWED,
                    ),
                )
                for index in range(65)
            )
            return HybridSearchResponse(
                query=request.query,
                release_id="release-1",
                rrf_k=60,
                degraded=False,
                channel_reports=(
                    HybridChannelReport(channel=HybridChannel.FULLTEXT, status=HybridChannelStatus.OK, hit_count=65),
                    HybridChannelReport(channel=HybridChannel.VECTOR, status=HybridChannelStatus.EMPTY),
                ),
                hits=hits,
                evidence_status=SearchStatus.SUPPORTED,
                message="已检索到可引用证据",
            )

    service = StructuredSearchService(FakeHybrid())
    first_request = StructuredSearchRequest(query="古桥", page_size=25, candidate_k=100)
    first = await service.search(first_request)
    second = await service.search(first_request.model_copy(update={"cursor": first.next_cursor}))
    third = await service.search(first_request.model_copy(update={"cursor": second.next_cursor}))

    ids = [hit.chunk_id for page in (first, second, third) for hit in page.hits]
    assert len(ids) == len(set(ids)) == 65
    assert [first.returned_count, second.returned_count, third.returned_count] == [25, 25, 15]
    assert first.has_more is True
    assert third.has_more is False
    assert third.next_cursor is None

    changed = first_request.model_copy(
        update={
            "filters": StructuredSearchFilters(dynasties=(Dynasty.MING,)),
            "cursor": first.next_cursor,
        }
    )
    with pytest.raises(StructuredSearchCursorError, match="different query"):
        await service.search(changed)
