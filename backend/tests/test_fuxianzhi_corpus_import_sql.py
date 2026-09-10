from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import ReviewStatus
from wu_culture.chunking import ChunkingPolicy
from wu_culture.corpus_import import build_import_bundle, scan_corpus
from wu_culture.fulltext import FullTextSearchRequest
from wu_culture.ingestion import IngestionStepName, begin_step, complete_step
from wu_culture.releases import PublishReleaseRequest
from wu_culture.review import ReviewBatchRequest, ReviewRequest, ReviewTargetType

from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture import (
    ChunkSetRow,
    CleanedOcrPageRow,
    CorpusImportBatchRow,
    CorpusImportItemRow,
    CorpusQualityIssueRow,
    EvidenceRow,
    FullTextDocumentRow,
    FullTextIndexStateRow,
    IngestionEventRow,
    IngestionJobRow,
    IngestionStepRow,
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
    SqlCorpusImportRepository,
    SqlFullTextRepository,
    SqlIngestionJobRepository,
    SqlKnowledgeReleaseRepository,
    SqlReviewRepository,
    TextChunkRow,
    TextCleaningChangeRow,
)


def _write_bundle(bundle_dir) -> None:
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "book.pdf").write_bytes(b"%PDF-1.4\nfixture")
    for name, body in {
        "text_raw_简体.txt": "原始简体",
        "text_raw_繁体.txt": "原始繁體",
        "text_简体.txt": "清理简体",
        "text_繁体.txt": "清理繁體",
    }.items():
        (bundle_dir / name).write_text(f"===== 第 1 页 (folio 一) =====\n{body}", encoding="utf-8")
    for name in ("text_简体.html", "text_繁体.html"):
        (bundle_dir / name).write_text("<p>fixture</p>", encoding="utf-8")


def test_sql_corpus_import_is_atomic_and_idempotent(tmp_path):
    asyncio.run(_exercise_sql_corpus_import(tmp_path))


async def _exercise_sql_corpus_import(tmp_path):
    corpus_root = tmp_path / "corpus"
    _write_bundle(corpus_root / "苏州" / "SQL 导入样本")
    scanned = scan_corpus(corpus_root).bundles[0]
    manifest = scanned.model_copy(update={"source_level": "B", "source_institution": "测试馆", "holder": "测试馆"})
    imported = build_import_bundle(
        corpus_root,
        manifest,
        actor_id="admin-1",
        generated_at=datetime(2026, 8, 22, tzinfo=UTC),
        chunking_policy=ChunkingPolicy(split_version="fuxianzhi-v1", max_characters=200, overlap_characters=20),
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'corpus-import.db'}")
    tables = [
        ObjectMetadataRow.__table__,
        SourceDocumentRow.__table__,
        SourceFileRow.__table__,
        OcrPageAttemptRow.__table__,
        CleanedOcrPageRow.__table__,
        TextCleaningChangeRow.__table__,
        ChunkSetRow.__table__,
        TextChunkRow.__table__,
        IngestionJobRow.__table__,
        IngestionStepRow.__table__,
        IngestionEventRow.__table__,
        CorpusImportBatchRow.__table__,
        CorpusImportItemRow.__table__,
        CorpusQualityIssueRow.__table__,
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
    repository = SqlCorpusImportRepository(session_factory)

    try:
        first = await repository.import_bundle(
            batch_id="corpus-batch-1",
            manifest_sha256="a" * 64,
            corpus_root_id="fuxianzhi",
            bundle_id=manifest.bundle_id,
            imported=imported,
            actor_id="admin-1",
            imported_at=datetime(2026, 8, 22, tzinfo=UTC),
        )
        second = await repository.import_bundle(
            batch_id="corpus-batch-1",
            manifest_sha256="a" * 64,
            corpus_root_id="fuxianzhi",
            bundle_id=manifest.bundle_id,
            imported=imported,
            actor_id="admin-1",
            imported_at=datetime(2026, 8, 22, tzinfo=UTC),
        )

        assert first.imported is True
        assert second.imported is False
        assert second.item_id == first.item_id
        review_queue = await SqlReviewRepository(session_factory).get_queue(
            source_file_id=imported.source_file.id,
            chunk_set_id=imported.chunk_set.id,
        )
        assert review_queue.pages[0].page_number == 1
        assert review_queue.pages[0].folio_label == "一"
        review_repository = SqlReviewRepository(session_factory)
        await review_repository.review_many(
            document_id=imported.document.id,
            source_file_id=imported.source_file.id,
            batch=ReviewBatchRequest(
                items=tuple(
                    ReviewRequest(
                        target_type=target_type,
                        target_id=target_id,
                        decision=ReviewStatus.REVIEWED,
                    )
                    for target_type, target_id in (
                        *((ReviewTargetType.PAGE, page.id) for page in review_queue.pages),
                        *((ReviewTargetType.CHUNK, chunk.id) for chunk in review_queue.chunks),
                    )
                )
            ),
            reviewed_by="admin-1",
            reviewed_at=datetime(2026, 8, 22, tzinfo=UTC),
            batch_id="review-corpus-batch-1",
        )
        gate = await review_repository.chunk_set_publication_gate(
            source_file_id=imported.source_file.id,
            chunk_set_id=imported.chunk_set.id,
        )
        assert gate.allowed is True

        ingestion_repository = SqlIngestionJobRepository(session_factory)
        job = await ingestion_repository.get(imported.ingestion_job.id)
        assert job is not None
        running, started_event = begin_step(
            job,
            step_name=IngestionStepName.REVIEW,
            worker_id="reviewer:admin-1",
            now=datetime(2026, 8, 22, tzinfo=UTC),
        )
        await ingestion_repository.save(running, started_event, expected_version=job.version)
        reviewed_job, completed_event = complete_step(
            running,
            step_name=IngestionStepName.REVIEW,
            output_ref=f"chunk-set:{imported.chunk_set.id}",
            now=datetime(2026, 8, 22, tzinfo=UTC),
        )
        await ingestion_repository.save(reviewed_job, completed_event, expected_version=running.version)

        async with session_factory() as session:
            source = await session.get(SourceDocumentRow, imported.document.id)
            source.authorization_status = "active"
            source.authorization_basis = "synthetic test authorization"
            source.visibility_scope = "public"
            source.authorized_uses_json = '["public_quote"]'
            await session.commit()
        fulltext_repository = SqlFullTextRepository(session_factory)
        release_repository = SqlKnowledgeReleaseRepository(
            session_factory,
            publication_indexer=fulltext_repository,
        )
        release = await release_repository.publish(
            PublishReleaseRequest(
                chunk_set_ids=(imported.chunk_set.id,),
                release_notes="府县志合成导入验收",
                expected_state_version=0,
            ),
            actor_id="admin-1",
            created_at=datetime(2026, 8, 22, tzinfo=UTC),
        )
        search = await fulltext_repository.search(FullTextSearchRequest(query="清理繁體", release_id=release.id))
        assert search.total == 1
        assert search.hits[0].citation.source_file_id == imported.source_file.id
        assert search.hits[0].citation.page_start == 1
        assert search.hits[0].citation.folio_start == "一"
        batches = await repository.list_batches()
        items = await repository.list_items("corpus-batch-1")
        assert batches[0]["item_count"] == 1
        assert batches[0]["page_count"] == 1
        assert items[0]["bundle_id"] == manifest.bundle_id
        async with session_factory() as session:
            for row_type in (
                SourceDocumentRow,
                SourceFileRow,
                OcrPageAttemptRow,
                CleanedOcrPageRow,
                ChunkSetRow,
                TextChunkRow,
                IngestionJobRow,
                CorpusImportItemRow,
            ):
                assert await session.scalar(select(func.count()).select_from(row_type)) == 1
            attempt = await session.get(OcrPageAttemptRow, imported.ocr_attempts[0].id)
            assert attempt.folio_label == "一"
            assert attempt.image_sha256 is None
            assert attempt.image_width is None
            assert attempt.image_height is None
    finally:
        await engine.dispose()
