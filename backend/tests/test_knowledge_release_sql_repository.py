from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_text_review_sql_repository import _seed_review_targets
from wu_culture import ReviewStatus
from wu_culture.releases import (
    KnowledgeReleaseConflict,
    KnowledgeReleaseGateError,
    KnowledgeReleasePreparationError,
    PublishReleaseRequest,
    ReleaseStatus,
    RetryReleaseRequest,
    RollbackReleaseRequest,
)
from wu_culture.review import ReviewBatchRequest, ReviewRequest, ReviewTargetType

from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.operations import OperationsRepository
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
    SqlFullTextRepository,
    SqlKnowledgeReleaseRepository,
    SqlReviewRepository,
    TextChunkRow,
    TextCleaningChangeRow,
)
from deerflow.persistence.wu_culture.model import WuEntityRow

NOW = datetime(2026, 7, 21, 16, 0, tzinfo=UTC)


def test_publish_switch_rollback_and_failed_gate_are_atomic(tmp_path) -> None:
    asyncio.run(_exercise_repository(tmp_path))


def test_preparation_failure_rolls_back_index_and_asset_rows_before_retry(tmp_path) -> None:
    asyncio.run(_exercise_preparation_rollback(tmp_path))


async def _exercise_repository(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'releases.db'}")
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
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _seed_review_targets(session_factory)
    review_repository = SqlReviewRepository(session_factory)
    await review_repository.review_many(
        document_id="document-1",
        source_file_id="file-1",
        batch=ReviewBatchRequest(
            items=(
                ReviewRequest(target_type=ReviewTargetType.PAGE, target_id="cleaned-page-1", decision=ReviewStatus.REVIEWED),
                ReviewRequest(target_type=ReviewTargetType.CHUNK, target_id="chunk-1", decision=ReviewStatus.REVIEWED),
            )
        ),
        reviewed_by="admin-1",
        reviewed_at=NOW,
        batch_id="batch-1",
    )
    repository = SqlKnowledgeReleaseRepository(session_factory)

    try:
        assert (await repository.get_state()).state_version == 0
        broken_repository = SqlKnowledgeReleaseRepository(session_factory, publication_indexer=_BrokenIndexer())
        with pytest.raises(KnowledgeReleasePreparationError, match="index failed"):
            await broken_repository.publish(
                PublishReleaseRequest(chunk_set_ids=("chunk-set-1",), release_notes="失败版本", expected_state_version=0),
                actor_id="admin-1",
                created_at=NOW,
            )
        failed_releases = await repository.list_releases()
        assert len(failed_releases) == 1
        assert failed_releases[0].status is ReleaseStatus.FAILED
        assert failed_releases[0].failure_code == "RuntimeError"
        assert failed_releases[0].failure_message == "index failed"
        assert (await repository.get_state()).state_version == 0

        first = await repository.retry(
            failed_releases[0].id,
            RetryReleaseRequest(expected_state_version=0),
            actor_id="admin-1",
            changed_at=NOW,
        )
        assert first.version == "v1"
        assert first.status is ReleaseStatus.ACTIVE
        assert [item.chunk_id for item in first.items] == ["chunk-1"]
        assert (await repository.get_active()).id == first.id
        assert (await repository.get_state()).state_version == 1

        await _add_chunk_set(session_factory, suffix="2", review_status="reviewed")
        second = await repository.publish(
            PublishReleaseRequest(chunk_set_ids=("chunk-set-2",), release_notes="第二版", expected_state_version=1),
            actor_id="admin-1",
            created_at=NOW,
        )
        assert second.version == "v2"
        assert second.status is ReleaseStatus.ACTIVE
        assert (await repository.get(first.id)).status is ReleaseStatus.READY
        assert (await repository.get_state()).active_release_id == second.id

        rolled_back = await repository.rollback(
            RollbackReleaseRequest(target_release_id=first.id, expected_state_version=2, reason="第二版需重新校对"),
            actor_id="admin-2",
            changed_at=NOW,
        )
        assert rolled_back.active_release_id == first.id
        assert rolled_back.state_version == 3
        assert [event.action.value for event in await repository.list_events()] == ["publish", "publish", "rollback"]

        with pytest.raises(KnowledgeReleaseConflict):
            await repository.rollback(
                RollbackReleaseRequest(target_release_id=first.id, expected_state_version=2, reason="过期请求"),
                actor_id="admin-2",
                changed_at=NOW,
            )

        await _add_chunk_set(session_factory, suffix="3", review_status="pending")
        before = await repository.list_releases()
        with pytest.raises(KnowledgeReleaseGateError):
            await repository.publish(
                PublishReleaseRequest(chunk_set_ids=("chunk-set-3",), release_notes="不应成功", expected_state_version=3),
                actor_id="admin-1",
                created_at=NOW,
            )
        assert await repository.list_releases() == before
        assert (await repository.get_state()).active_release_id == first.id

        async with session_factory() as session:
            await session.execute(
                update(SourceDocumentRow)
                .where(SourceDocumentRow.id == "document-1")
                .values(
                    authorization_status="active",
                    authorization_basis="Project owner approved internal processing",
                    visibility_scope="internal",
                    authorized_uses_json='["internal_processing"]',
                )
            )
            await session.commit()
        working = await repository.publish(
            PublishReleaseRequest(
                chunk_set_ids=("chunk-set-3",),
                release_notes="府县志内部工作版本",
                expected_state_version=3,
                scope="internal",
            ),
            actor_id="admin-1",
            created_at=NOW,
        )
        assert working.scope == "internal"
        assert working.items[0].chunk_id == "chunk-3"
        assert (await repository.get_active()).scope == "internal"
    finally:
        await engine.dispose()


class _BrokenIndexer:
    async def index_release(self, session, release, *, indexed_at):
        raise RuntimeError("index failed")


class _FailAfterAssets:
    def __init__(self, delegate: OperationsRepository) -> None:
        self._delegate = delegate

    async def prepare_release(self, session, release, *, actor_id, created_at):
        await self._delegate.prepare_release(
            session,
            release,
            actor_id=actor_id,
            created_at=created_at,
        )
        raise RuntimeError("asset finalization failed")

    async def ensure_release_ready(self, session, release):
        await self._delegate.ensure_release_ready(session, release)


async def _exercise_preparation_rollback(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'release-rollback.db'}")
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
        WuEntityRow.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=tables,
            )
        )
        await connection.execute(
            text(
                """CREATE TABLE wu_asset_versions (
                    id TEXT PRIMARY KEY,
                    knowledge_release_id TEXT UNIQUE NOT NULL,
                    knowledge_release_version TEXT NOT NULL,
                    graph_manifest_sha256 TEXT NOT NULL,
                    map_manifest_sha256 TEXT NOT NULL,
                    entity_count INTEGER NOT NULL,
                    map_point_count INTEGER NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at DATETIME NOT NULL
                )"""
            )
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _seed_review_targets(session_factory)
    await SqlReviewRepository(session_factory).review_many(
        document_id="document-1",
        source_file_id="file-1",
        batch=ReviewBatchRequest(
            items=(
                ReviewRequest(
                    target_type=ReviewTargetType.PAGE,
                    target_id="cleaned-page-1",
                    decision=ReviewStatus.REVIEWED,
                ),
                ReviewRequest(
                    target_type=ReviewTargetType.CHUNK,
                    target_id="chunk-1",
                    decision=ReviewStatus.REVIEWED,
                ),
            )
        ),
        reviewed_by="admin-1",
        reviewed_at=NOW,
        batch_id="review-atomic-preparation",
    )
    fulltext = SqlFullTextRepository(session_factory)
    assets = OperationsRepository(
        session_factory,
        publication_map_manifest={"points": [{"id": "point-1"}]},
    )
    failing_repository = SqlKnowledgeReleaseRepository(
        session_factory,
        publication_indexer=fulltext,
        publication_assets=_FailAfterAssets(assets),
    )
    try:
        with pytest.raises(
            KnowledgeReleasePreparationError,
            match="asset finalization failed",
        ):
            await failing_repository.publish(
                PublishReleaseRequest(
                    chunk_set_ids=("chunk-set-1",),
                    release_notes="原子准备测试",
                    expected_state_version=0,
                ),
                actor_id="admin-1",
                created_at=NOW,
            )
        failed = (await failing_repository.list_releases())[0]
        assert failed.status is ReleaseStatus.FAILED
        assert failed.preparation_attempts == 1
        assert (await failing_repository.get_state()).active_release_id is None

        async with engine.connect() as connection:
            counts = {
                table: (
                    await connection.execute(
                        text(
                            f"SELECT COUNT(*) FROM {table} WHERE "
                            f"{column}=:release_id"
                        ),
                        {"release_id": failed.id},
                    )
                ).scalar_one()
                for table, column in (
                    ("wu_fulltext_documents", "release_id"),
                    ("wu_fulltext_index_states", "release_id"),
                    ("wu_search_filter_metadata", "release_id"),
                    ("wu_asset_versions", "knowledge_release_id"),
                )
            }
            counts["wu_evidence"] = (
                await connection.execute(text("SELECT COUNT(*) FROM wu_evidence"))
            ).scalar_one()
        assert counts == {
            "wu_fulltext_documents": 0,
            "wu_fulltext_index_states": 0,
            "wu_search_filter_metadata": 0,
            "wu_evidence": 0,
            "wu_asset_versions": 0,
        }

        repository = SqlKnowledgeReleaseRepository(
            session_factory,
            publication_indexer=fulltext,
            publication_assets=assets,
        )
        active = await repository.retry(
            failed.id,
            RetryReleaseRequest(expected_state_version=0),
            actor_id="admin-1",
            changed_at=NOW,
        )
        assert active.status is ReleaseStatus.ACTIVE
        assert active.preparation_attempts == 2
        assert (await repository.get_state()).active_release_id == active.id
        async with engine.connect() as connection:
            assert (
                await connection.execute(
                    text(
                        "SELECT COUNT(*) FROM wu_asset_versions "
                        "WHERE knowledge_release_id=:release_id"
                    ),
                    {"release_id": active.id},
                )
            ).scalar_one() == 1
            assert (
                await connection.execute(
                    text(
                        "SELECT COUNT(*) FROM wu_fulltext_index_states "
                        "WHERE release_id=:release_id AND status='ready'"
                    ),
                    {"release_id": active.id},
                )
            ).scalar_one() == 1
    finally:
        await engine.dispose()


async def _add_chunk_set(session_factory, *, suffix: str, review_status: str) -> None:
    async with session_factory() as session:
        session.add(
            ChunkSetRow(
                id=f"chunk-set-{suffix}",
                document_id="document-1",
                source_file_id="file-1",
                split_version=f"split-v{suffix}",
                policy_json=f'{{"split_version":"split-v{suffix}","max_characters":1000,"overlap_characters":100}}',
                structure_json="[]",
                input_sha256=suffix[0] * 64,
                generated_by="admin-1",
                generated_at=NOW,
            )
        )
        session.add(
            TextChunkRow(
                id=f"chunk-{suffix}",
                document_id="document-1",
                source_file_id="file-1",
                chunk_set_id=f"chunk-set-{suffix}",
                split_version=f"split-v{suffix}",
                chunk_index=0,
                volume="卷一",
                section="目一",
                item="目一",
                paragraph="0",
                paragraph_index=0,
                paragraph_char_start=0,
                paragraph_char_end=4,
                original_text="木渎沿河。",
                normalized_text="木渎沿河。",
                page_start=1,
                page_end=1,
                cleaned_page_ids_json='["cleaned-page-1"]',
                content_sha256=suffix[0] * 64,
                review_status=review_status,
            )
        )
        await session.commit()
