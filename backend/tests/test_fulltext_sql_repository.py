from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_text_review_sql_repository import _seed_review_targets
from wu_culture import EntityType, ReviewStatus
from wu_culture.filters import Dynasty, StructuredSearchFilters
from wu_culture.fulltext import FullTextSearchRequest
from wu_culture.releases import PublishReleaseRequest
from wu_culture.review import ReviewBatchRequest, ReviewRequest, ReviewTargetType

from deerflow.agents.xingxi.tools import build_search_sources_tool
from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture import (
    ChunkSetRow,
    CleanedOcrPageRow,
    EvidenceRow,
    FullTextDocumentRow,
    FullTextIndexStateRow,
    KnowledgeReleaseEventRow,
    KnowledgeReleaseItemRow,
    KnowledgeReleaseRow,
    KnowledgeReleaseStateRow,
    OcrPageAttemptRow,
    ReviewRecordRow,
    SearchFilterFacetRow,
    SearchFilterMetadataRow,
    SourceDocumentRow,
    SourceFileRow,
    SqlEvidenceRepository,
    SqlFullTextRepository,
    SqlKnowledgeReleaseRepository,
    SqlReviewRepository,
    TextChunkRow,
    TextCleaningChangeRow,
)

NOW = datetime(2026, 7, 21, 18, 0, tzinfo=UTC)


def test_release_index_search_phrase_keywords_filters_pagination_and_injection(tmp_path) -> None:
    asyncio.run(_exercise_repository(tmp_path))


async def _exercise_repository(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fulltext.db'}")
    tables = [
        SourceDocumentRow.__table__,
        ObjectMetadataRow.__table__,
        SourceFileRow.__table__,
        OcrPageAttemptRow.__table__,
        CleanedOcrPageRow.__table__,
        TextCleaningChangeRow.__table__,
        ChunkSetRow.__table__,
        TextChunkRow.__table__,
        ReviewRecordRow.__table__,
        KnowledgeReleaseRow.__table__,
        KnowledgeReleaseItemRow.__table__,
        KnowledgeReleaseStateRow.__table__,
        KnowledgeReleaseEventRow.__table__,
        FullTextDocumentRow.__table__,
        FullTextIndexStateRow.__table__,
        SearchFilterMetadataRow.__table__,
        SearchFilterFacetRow.__table__,
        EvidenceRow.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _seed_review_targets(session_factory)
    async with session_factory() as session:
        source = await session.get(SourceDocumentRow, "document-1")
        source.authorization_status = "active"
        source.authorization_basis = "测试授权"
        source.authorized_uses_json = '["internal_processing","public_quote"]'
        source.visibility_scope = "public"
        await session.commit()
    await _add_search_chunks(session_factory)
    review = SqlReviewRepository(session_factory)
    await review.review_many(
        document_id="document-1",
        source_file_id="file-1",
        batch=ReviewBatchRequest(
            items=(
                ReviewRequest(target_type=ReviewTargetType.PAGE, target_id="cleaned-page-1", decision=ReviewStatus.REVIEWED),
                ReviewRequest(target_type=ReviewTargetType.CHUNK, target_id="chunk-1", decision=ReviewStatus.REVIEWED),
                ReviewRequest(target_type=ReviewTargetType.CHUNK, target_id="chunk-2", decision=ReviewStatus.REVIEWED),
                ReviewRequest(target_type=ReviewTargetType.CHUNK, target_id="chunk-3", decision=ReviewStatus.REVIEWED),
            )
        ),
        reviewed_by="admin-1",
        reviewed_at=NOW,
        batch_id="review-search",
    )
    fulltext = SqlFullTextRepository(session_factory)
    releases = SqlKnowledgeReleaseRepository(session_factory, publication_indexer=fulltext)

    try:
        release = await releases.publish(
            PublishReleaseRequest(chunk_set_ids=("chunk-set-1",), release_notes="全文索引首版", expected_state_version=0),
            actor_id="admin-1",
            created_at=NOW,
        )
        async with session_factory() as session:
            metadata = {row.chunk_id: row for row in (await session.execute(select(SearchFilterMetadataRow).where(SearchFilterMetadataRow.release_id == release.id))).scalars().all()}
            metadata["chunk-1"].spatial_confidence = 0.4
            metadata["chunk-2"].spatial_confidence = 0.9
            metadata["chunk-3"].spatial_confidence = 0.5
            session.add_all(
                [
                    SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-1", facet_type="dynasty", facet_value="ming"),
                    SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-2", facet_type="dynasty", facet_value="qing"),
                    SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-2", facet_type="entity_type", facet_value="bridge"),
                    SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-3", facet_type="dynasty", facet_value="qing"),
                    SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-3", facet_type="entity_type", facet_value="waterway"),
                ]
            )
            await session.commit()

        phrase = await fulltext.search(FullTextSearchRequest(query='"香溪沿岸"'))
        assert phrase.release_id == release.id
        assert phrase.total == 1
        assert phrase.hits[0].chunk_id == "chunk-2"
        assert "【香溪沿岸】" in phrase.hits[0].snippet
        assert phrase.hits[0].citation.page_start == 2
        assert phrase.hits[0].citation.document_title == "木渎小志"

        proper_noun = await fulltext.search(FullTextSearchRequest(query="木渎", page=1, page_size=1))
        assert proper_noun.total == 3
        assert proper_noun.hits[0].chunk_id == "chunk-1"
        assert proper_noun.hits[0].citation.source_file_id == "file-1"
        assert proper_noun.hits[0].citation.folio_start == "一"
        assert proper_noun.hits[0].citation.folio_end == "一"
        second_page = await fulltext.search(FullTextSearchRequest(query="木渎", page=2, page_size=1))
        assert second_page.total == 3
        assert second_page.hits[0].chunk_id != proper_noun.hits[0].chunk_id

        keywords = await fulltext.search(FullTextSearchRequest(query="木渎 古桥"))
        assert [hit.chunk_id for hit in keywords.hits] == ["chunk-3"]

        natural_language = await fulltext.search(FullTextSearchRequest(query="木渎建了什么"))
        assert natural_language.total >= 1
        assert any("木渎" in hit.snippet for hit in natural_language.hits)

        cross_script = await fulltext.search(FullTextSearchRequest(query="旧镇"))
        assert [hit.chunk_id for hit in cross_script.hits] == ["chunk-3"]
        assert "【舊鎮】" in cross_script.hits[0].snippet

        filtered = await fulltext.search(FullTextSearchRequest(query="木渎", document_ids=("other-document",)))
        assert filtered.total == 0
        assert filtered.hits == ()

        structured = await fulltext.search(
            FullTextSearchRequest(
                query="木渎",
                filters=StructuredSearchFilters(
                    editions=("测试版",),
                    dynasties=(Dynasty.QING,),
                    entity_types=(EntityType.BRIDGE,),
                    min_spatial_confidence=0.8,
                ),
            )
        )
        assert [hit.chunk_id for hit in structured.hits] == ["chunk-2"]

        reviewed_only = await fulltext.search(
            FullTextSearchRequest(
                query="木渎",
                filters=StructuredSearchFilters(review_statuses=(ReviewStatus.REVIEWED,)),
            )
        )
        assert reviewed_only.total == 3
        disputed_only = await fulltext.search(
            FullTextSearchRequest(
                query="木渎",
                filters=StructuredSearchFilters(review_statuses=(ReviewStatus.DISPUTED,)),
            )
        )
        assert disputed_only.hits == ()

        mutually_exclusive = await fulltext.search(
            FullTextSearchRequest(
                query="木渎",
                filters=StructuredSearchFilters(
                    dynasties=(Dynasty.QING,),
                    entity_types=(EntityType.BRIDGE,),
                    max_spatial_confidence=0.6,
                ),
            )
        )
        assert mutually_exclusive.hits == ()

        injected_filter = await fulltext.search(
            FullTextSearchRequest(
                query="木渎",
                filters=StructuredSearchFilters(editions=("测试版') OR 1=1 --",)),
            )
        )
        assert injected_filter.hits == ()

        special = await fulltext.search(FullTextSearchRequest(query="%' OR 1=1 --"))
        assert special.total == 0

        tool_result = await build_search_sources_tool(fulltext_repository=fulltext).ainvoke({"query": "香溪沿岸", "source_levels": ["A"], "top_k": 1})
        assert tool_result["status"] == "supported"
        assert tool_result["release_id"] == release.id
        assert tool_result["hits"][0]["citation"]["page_start"] == 2
        evidence_id = tool_result["hits"][0]["evidence_id"]
        evidence = await SqlEvidenceRepository(session_factory).get_evidence(evidence_id)
        assert evidence is not None
        assert "香溪沿岸" in evidence.evidence.quote
        assert evidence.evidence.chunk_id == "chunk-2"

        async with session_factory() as session:
            source = await session.get(SourceDocumentRow, "document-1")
            source.authorization_status = "revoked"
            await session.commit()
        revoked = await fulltext.search(FullTextSearchRequest(query="木渎"))
        assert revoked.total == 0
    finally:
        await engine.dispose()


async def _add_search_chunks(session_factory) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                TextChunkRow(
                    id="chunk-2",
                    document_id="document-1",
                    source_file_id="file-1",
                    chunk_set_id="chunk-set-1",
                    split_version="split-v1",
                    chunk_index=1,
                    volume="卷一",
                    section="桥梁",
                    item="桥梁",
                    paragraph="1",
                    paragraph_index=1,
                    paragraph_char_start=0,
                    paragraph_char_end=18,
                    original_text="木渎香溪沿岸有虹桥、永安桥。",
                    normalized_text="木渎香溪沿岸有虹桥、永安桥。",
                    page_start=2,
                    page_end=2,
                    cleaned_page_ids_json='["cleaned-page-1"]',
                    content_sha256="2" * 64,
                    review_status="pending",
                ),
                TextChunkRow(
                    id="chunk-3",
                    document_id="document-1",
                    source_file_id="file-1",
                    chunk_set_id="chunk-set-1",
                    split_version="split-v1",
                    chunk_index=2,
                    volume="卷二",
                    section="古桥",
                    item="古桥",
                    paragraph="2",
                    paragraph_index=2,
                    paragraph_char_start=0,
                    paragraph_char_end=16,
                    original_text="木瀆舊鎮另有古橋跨河。",
                    normalized_text="木瀆舊鎮另有古橋跨河。",
                    page_start=3,
                    page_end=3,
                    cleaned_page_ids_json='["cleaned-page-1"]',
                    content_sha256="3" * 64,
                    review_status="pending",
                ),
            ]
        )
        await session.commit()
