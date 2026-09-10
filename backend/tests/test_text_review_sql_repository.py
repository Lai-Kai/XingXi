from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import ReviewStatus
from wu_culture.review import ReviewBatchRequest, ReviewRequest, ReviewTargetNotFound, ReviewTargetType

from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture import (
    ChunkSetRow,
    CleanedOcrPageRow,
    OcrPageAttemptRow,
    ReviewRecordRow,
    SourceDocumentRow,
    SourceFileRow,
    SqlReviewRepository,
    TextChunkRow,
    TextCleaningChangeRow,
)

NOW = datetime(2026, 7, 21, 13, 0, tzinfo=UTC)


def test_review_batch_history_gate_and_atomic_rollback(tmp_path):
    asyncio.run(_exercise_repository(tmp_path))


async def _exercise_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'review.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[
                    SourceDocumentRow.__table__,
                    ObjectMetadataRow.__table__,
                    SourceFileRow.__table__,
                    OcrPageAttemptRow.__table__,
                    CleanedOcrPageRow.__table__,
                    TextCleaningChangeRow.__table__,
                    ChunkSetRow.__table__,
                    TextChunkRow.__table__,
                    ReviewRecordRow.__table__,
                ],
            )
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await _seed_review_targets(session_factory)
    repository = SqlReviewRepository(session_factory)
    approved_batch = ReviewBatchRequest(
        items=(
            ReviewRequest(target_type=ReviewTargetType.PAGE, target_id="cleaned-page-1", decision=ReviewStatus.REVIEWED),
            ReviewRequest(target_type=ReviewTargetType.CHUNK, target_id="chunk-1", decision=ReviewStatus.REVIEWED),
        )
    )

    try:
        approved = await repository.review_many(
            document_id="document-1",
            source_file_id="file-1",
            batch=approved_batch,
            reviewed_by="admin-1",
            reviewed_at=NOW,
            batch_id="batch-1",
        )
        assert [record.revision for record in approved] == [1, 1]
        queue = await repository.get_queue(source_file_id="file-1", chunk_set_id="chunk-set-1")
        assert queue.pages[0].raw_text == queue.pages[0].clean_text
        assert queue.pages[0].ocr_confidence == 0.95
        assert queue.pages[0].review_status is ReviewStatus.REVIEWED
        assert queue.chunks[0].cleaned_page_ids == ("cleaned-page-1",)
        assert (await repository.chunk_set_publication_gate(source_file_id="file-1", chunk_set_id="chunk-set-1")).allowed is True
        assert (await repository.publication_gate(source_file_id="file-1", chunk_id="chunk-1")).allowed is True

        disputed = await repository.review_many(
            document_id="document-1",
            source_file_id="file-1",
            batch=ReviewBatchRequest(
                items=(
                    ReviewRequest(
                        target_type=ReviewTargetType.PAGE,
                        target_id="cleaned-page-1",
                        decision=ReviewStatus.DISPUTED,
                        comment="异体字待专家确认",
                    ),
                )
            ),
            reviewed_by="admin-2",
            reviewed_at=NOW,
            batch_id="batch-2",
        )
        assert disputed[0].revision == 2
        assert disputed[0].previous_status is ReviewStatus.REVIEWED
        assert (await repository.publication_gate(source_file_id="file-1", chunk_id="chunk-1")).reasons == ("page_not_reviewed",)
        page_history = await repository.list_records(
            source_file_id="file-1",
            target_type=ReviewTargetType.PAGE,
            target_id="cleaned-page-1",
        )
        assert [record.decision for record in page_history] == [ReviewStatus.REVIEWED, ReviewStatus.DISPUTED]

        before = await repository.list_records(source_file_id="file-1")
        with pytest.raises(ReviewTargetNotFound):
            await repository.review_many(
                document_id="document-1",
                source_file_id="file-1",
                batch=ReviewBatchRequest(
                    items=(
                        ReviewRequest(
                            target_type=ReviewTargetType.CHUNK,
                            target_id="chunk-1",
                            decision=ReviewStatus.REJECTED,
                            comment="退回",
                        ),
                        ReviewRequest(
                            target_type=ReviewTargetType.CHUNK,
                            target_id="missing-chunk",
                            decision=ReviewStatus.REVIEWED,
                        ),
                    )
                ),
                reviewed_by="admin-1",
                reviewed_at=NOW,
                batch_id="batch-invalid",
            )
        assert await repository.list_records(source_file_id="file-1") == before
        assert (await repository.publication_gate(source_file_id="file-1", chunk_id="chunk-1")).reasons == ("page_not_reviewed",)
    finally:
        await engine.dispose()


async def _seed_review_targets(session_factory):
    raw_text = "卷一\n目一\n木渎沿河。"
    digest = hashlib.sha256(raw_text.encode()).hexdigest()
    async with session_factory() as session:
        session.add(
            SourceDocumentRow(
                id="document-1",
                title="木渎小志",
                edition="测试版",
                source_type="gazetteer",
                source_level="A",
                copyright_status="unknown",
                source_institution="测试机构",
                holder="测试机构",
                status="registered",
                authorization_status="unconfirmed",
                visibility_scope="internal",
                authorized_uses_json="[]",
                created_by="admin-1",
                created_at=NOW,
                updated_by="admin-1",
                updated_at=NOW,
            )
        )
        session.add(
            ObjectMetadataRow(
                object_key="sources/document-1/file-1.pdf",
                owner_id="document-1",
                kind="original",
                sha256="a" * 64,
                mime_type="application/pdf",
                size=100,
                backend="local",
                storage_uri="file:///objects/file-1.pdf",
                original_filename="木渎小志.pdf",
                created_at=NOW,
            )
        )
        session.add(
            SourceFileRow(
                id="file-1",
                document_id="document-1",
                object_key="sources/document-1/file-1.pdf",
                original_filename="木渎小志.pdf",
                mime_type="application/pdf",
                size=100,
                sha256="a" * 64,
                uploaded_by="admin-1",
                uploaded_at=NOW,
            )
        )
        session.add(
            OcrPageAttemptRow(
                id="ocr-page-1",
                source_file_id="file-1",
                page_number=1,
                attempt_number=1,
                folio_label="一",
                image_sha256="b" * 64,
                image_width=100,
                image_height=100,
                provider_name="test",
                model_name="test",
                languages_json='["zh-Hans"]',
                status="completed",
                raw_text=raw_text,
                mean_confidence=0.95,
                rotation_degrees=0,
                created_at=NOW,
            )
        )
        session.add(
            CleanedOcrPageRow(
                id="cleaned-page-1",
                source_file_id="file-1",
                ocr_attempt_id="ocr-page-1",
                page_number=1,
                generation_number=1,
                raw_text=raw_text,
                raw_sha256=digest,
                clean_text=raw_text,
                clean_sha256=digest,
                rule_version="clean-v1",
                script_conversion="preserve",
                policy_json='{"rule_version":"clean-v1"}',
                review_status="pending",
                generated_by="admin-1",
                generated_at=NOW,
            )
        )
        session.add(
            ChunkSetRow(
                id="chunk-set-1",
                document_id="document-1",
                source_file_id="file-1",
                split_version="split-v1",
                policy_json='{"split_version":"split-v1","max_characters":1000,"overlap_characters":100}',
                structure_json="[]",
                input_sha256=digest,
                generated_by="admin-1",
                generated_at=NOW,
            )
        )
        session.add(
            TextChunkRow(
                id="chunk-1",
                document_id="document-1",
                source_file_id="file-1",
                chunk_set_id="chunk-set-1",
                split_version="split-v1",
                chunk_index=0,
                volume="卷一",
                section="目一",
                item="目一",
                paragraph="0",
                paragraph_index=0,
                paragraph_char_start=0,
                paragraph_char_end=len(raw_text),
                original_text=raw_text,
                normalized_text=raw_text,
                page_start=1,
                page_end=1,
                cleaned_page_ids_json='["cleaned-page-1"]',
                content_sha256=digest,
                review_status="pending",
            )
        )
        await session.commit()
