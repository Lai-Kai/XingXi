from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_fulltext_sql_repository import _add_search_chunks
from test_text_review_sql_repository import _seed_review_targets
from wu_culture import EntityType, ReviewStatus
from wu_culture.filters import Dynasty, StructuredSearchFilters
from wu_culture.releases import PublishReleaseRequest
from wu_culture.review import ReviewBatchRequest, ReviewRequest, ReviewTargetType
from wu_culture.vectors import VectorIndexNotReady, VectorSearchRequest, begin_vector_index, complete_vector_index, fail_vector_index

from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.vector_extension import register_sqlite_vec
from deerflow.persistence.wu_culture import (
    ChunkSetRow,
    CleanedOcrPageRow,
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
    SqlFullTextRepository,
    SqlKnowledgeReleaseRepository,
    SqlReviewRepository,
    SqlVectorRepository,
    TextChunkRow,
    TextCleaningChangeRow,
    VectorEmbeddingRow,
    VectorIndexStateRow,
    VectorIndexVersionRow,
)

NOW = datetime(2026, 7, 21, 21, 0, tzinfo=UTC)


def test_vector_versions_switch_only_after_complete_and_never_mix_dimensions(tmp_path) -> None:
    asyncio.run(_exercise_repository(tmp_path))


async def _exercise_repository(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'vector.db'}")
    register_sqlite_vec(engine)
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
        VectorIndexVersionRow.__table__,
        VectorEmbeddingRow.__table__,
        VectorIndexStateRow.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _seed_review_targets(session_factory)
    await _add_search_chunks(session_factory)
    async with session_factory() as session:
        source = await session.get(SourceDocumentRow, "document-1")
        source.authorization_status = "active"
        source.authorization_basis = "测试授权"
        source.authorized_uses_json = '["public_quote"]'
        source.visibility_scope = "public"
        await session.commit()
    review = SqlReviewRepository(session_factory)
    await review.review_many(
        document_id="document-1",
        source_file_id="file-1",
        batch=ReviewBatchRequest(
            items=tuple(
                ReviewRequest(target_type=kind, target_id=target_id, decision=ReviewStatus.REVIEWED)
                for kind, target_id in (
                    (ReviewTargetType.PAGE, "cleaned-page-1"),
                    (ReviewTargetType.CHUNK, "chunk-1"),
                    (ReviewTargetType.CHUNK, "chunk-2"),
                    (ReviewTargetType.CHUNK, "chunk-3"),
                )
            )
        ),
        reviewed_by="admin-1",
        reviewed_at=NOW,
        batch_id="review-vector",
    )
    fulltext = SqlFullTextRepository(session_factory)
    release = await SqlKnowledgeReleaseRepository(session_factory, publication_indexer=fulltext).publish(
        PublishReleaseRequest(chunk_set_ids=("chunk-set-1",), release_notes="向量首版", expected_state_version=0),
        actor_id="admin-1",
        created_at=NOW,
    )
    repository = SqlVectorRepository(session_factory)
    manifest, build_items = await repository.get_release_build_items(release.id)
    assert manifest == release.manifest_sha256
    assert [item.chunk_id for item in build_items] == ["chunk-1", "chunk-2", "chunk-3"]
    vectors_v1 = (
        ("chunk-1", (0.0, 1.0, 0.0)),
        ("chunk-2", (1.0, 0.0, 0.0)),
        ("chunk-3", (0.8, 0.2, 0.0)),
    )
    async with session_factory() as session:
        metadata = {row.chunk_id: row for row in (await session.execute(select(SearchFilterMetadataRow).where(SearchFilterMetadataRow.release_id == release.id))).scalars().all()}
        metadata["chunk-2"].spatial_confidence = 0.95
        metadata["chunk-3"].spatial_confidence = 0.45
        session.add_all(
            [
                SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-2", facet_type="dynasty", facet_value="qing"),
                SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-2", facet_type="entity_type", facet_value="bridge"),
                SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-3", facet_type="dynasty", facet_value="qing"),
                SearchFilterFacetRow(release_id=release.id, chunk_id="chunk-3", facet_type="entity_type", facet_value="waterway"),
            ]
        )
        await session.commit()

    try:
        with pytest.raises(VectorIndexNotReady):
            await repository.search_by_vector(VectorSearchRequest(query="溪流旁的旧桥"), (1.0, 0.0, 0.0))

        building_v1 = begin_vector_index(
            index_id="vector-v1",
            release_id=release.id,
            release_manifest_sha256=release.manifest_sha256,
            embedding_model="test-embedding",
            embedding_version="v1",
            dimensions=3,
            created_by="admin-1",
            created_at=NOW,
        )
        await repository.create_build(building_v1, expected_state_version=0)
        ready_v1 = complete_vector_index(building_v1, item_count=3, completed_at=NOW)
        await repository.complete_build(ready_v1, vectors_v1)

        first = await repository.search_by_vector(VectorSearchRequest(query="溪流旁的旧桥", top_k=2), (1.0, 0.0, 0.0))
        assert first.index_id == "vector-v1"
        assert [hit.chunk_id for hit in first.hits] == ["chunk-2", "chunk-3"]
        assert first.hits[0].citation.page_start == 2
        assert first.hits[0].citation.source_file_id == "file-1"
        assert first.hits[0].citation.folio_start == "一"

        structured = await repository.search_by_vector(
            VectorSearchRequest(
                query="溪流旁的旧桥",
                top_k=2,
                filters=StructuredSearchFilters(
                    dynasties=(Dynasty.QING,),
                    entity_types=(EntityType.BRIDGE,),
                    min_spatial_confidence=0.8,
                ),
            ),
            (1.0, 0.0, 0.0),
        )
        assert [hit.chunk_id for hit in structured.hits] == ["chunk-2"]

        building_v2 = begin_vector_index(
            index_id="vector-v2",
            release_id=release.id,
            release_manifest_sha256=release.manifest_sha256,
            embedding_model="test-embedding",
            embedding_version="v2",
            dimensions=3,
            created_by="admin-1",
            created_at=NOW,
        )
        await repository.create_build(building_v2, expected_state_version=1)
        while_building = await repository.search_by_vector(VectorSearchRequest(query="溪流旁的旧桥", top_k=1), (1.0, 0.0, 0.0))
        assert while_building.index_id == "vector-v1"

        ready_v2 = complete_vector_index(building_v2, item_count=3, completed_at=NOW)
        await repository.complete_build(ready_v2, vectors_v1)
        switched = await repository.search_by_vector(VectorSearchRequest(query="溪流旁的旧桥", top_k=1), (1.0, 0.0, 0.0))
        assert switched.index_id == "vector-v2"
        assert (await repository.get_state(release.id)).state_version == 2

        building_v3 = begin_vector_index(
            index_id="vector-v3",
            release_id=release.id,
            release_manifest_sha256=release.manifest_sha256,
            embedding_model="test-embedding",
            embedding_version="v3",
            dimensions=3,
            created_by="admin-1",
            created_at=NOW,
        )
        await repository.create_build(building_v3, expected_state_version=2)
        await repository.fail_build(
            fail_vector_index(
                building_v3,
                error_code="ProviderUnavailable",
                error_message="temporary failure",
                failed_at=NOW,
            )
        )
        after_failure = await repository.search_by_vector(
            VectorSearchRequest(query="溪流旁的旧桥", top_k=1),
            (1.0, 0.0, 0.0),
        )
        assert after_failure.index_id == "vector-v2"
        assert (await repository.get_state(release.id)).state_version == 2

        with pytest.raises(ValueError, match="dimension"):
            await repository.search_by_vector(VectorSearchRequest(query="错误维度"), (1.0, 0.0))

        async with session_factory() as session:
            source = await session.get(SourceDocumentRow, "document-1")
            source.authorization_status = "revoked"
            await session.commit()
        revoked = await repository.search_by_vector(VectorSearchRequest(query="溪流旁的旧桥"), (1.0, 0.0, 0.0))
        assert revoked.hits == ()
    finally:
        await engine.dispose()
