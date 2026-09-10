from __future__ import annotations

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from wu_culture.corpus_import import CorpusImportBundle, CorpusImportCommitResult

from deerflow.persistence.object_storage import ObjectMetadataRow

from .model import (
    ChunkSetRow,
    CleanedOcrPageRow,
    CorpusImportBatchRow,
    CorpusImportItemRow,
    CorpusQualityIssueRow,
    OcrPageAttemptRow,
    SourceDocumentRow,
    SourceFileRow,
    TextChunkRow,
)
from .repository import SqlIngestionJobRepository, SqlSourceDocumentRepository


class SqlCorpusImportRepository:
    """Commit one corpus bundle atomically and resume by deterministic item ID."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def import_bundle(
        self,
        *,
        batch_id: str,
        manifest_sha256: str,
        corpus_root_id: str,
        bundle_id: str,
        imported: CorpusImportBundle,
        actor_id: str,
        imported_at,
    ) -> CorpusImportCommitResult:
        item_digest = hashlib.sha256(f"{manifest_sha256}\0{bundle_id}".encode()).hexdigest()
        item_id = f"corpus-item-{item_digest}"
        async with self._session_factory() as session:
            existing_item = await session.get(CorpusImportItemRow, item_id)
            if existing_item is not None:
                return CorpusImportCommitResult(
                    batch_id=batch_id,
                    item_id=item_id,
                    bundle_id=bundle_id,
                    imported=False,
                )
            batch = await session.get(CorpusImportBatchRow, batch_id)
            if batch is None:
                session.add(
                    CorpusImportBatchRow(
                        id=batch_id,
                        corpus_root_id=corpus_root_id,
                        manifest_sha256=manifest_sha256,
                        status="running",
                        created_by=actor_id,
                        created_at=imported_at,
                    )
                )
                await session.flush()
            elif batch.manifest_sha256 != manifest_sha256 or batch.corpus_root_id != corpus_root_id:
                raise ValueError("corpus import batch identity conflicts with an existing batch")

            await self._add_bundle_rows(session, imported)
            session.add(
                CorpusImportItemRow(
                    id=item_id,
                    batch_id=batch_id,
                    bundle_id=bundle_id,
                    document_id=imported.document.id,
                    source_file_id=imported.source_file.id,
                    chunk_set_id=imported.chunk_set.id,
                    page_count=len(imported.cleaned_pages),
                    quality_issue_count=len(imported.quality_issues),
                    status="completed",
                    imported_by=actor_id,
                    imported_at=imported_at,
                )
            )
            await session.flush()
            session.add_all(
                CorpusQualityIssueRow(
                    id=_quality_issue_id(item_id, issue.code, issue.field, issue.physical_page_number),
                    import_item_id=item_id,
                    bundle_id=bundle_id,
                    source_file_id=imported.source_file.id,
                    **issue.model_dump(mode="python"),
                )
                for issue in imported.quality_issues
            )
            await session.commit()
        return CorpusImportCommitResult(
            batch_id=batch_id,
            item_id=item_id,
            bundle_id=bundle_id,
            imported=True,
        )

    async def complete_batch(self, batch_id: str, *, completed_at) -> None:
        async with self._session_factory() as session:
            batch = await session.get(CorpusImportBatchRow, batch_id)
            if batch is None:
                raise ValueError("corpus import batch does not exist")
            batch.status = "completed"
            batch.completed_at = completed_at
            await session.commit()

    async def list_batches(self) -> list[dict]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(CorpusImportBatchRow).order_by(CorpusImportBatchRow.created_at.desc()))).scalars().all()
            results = []
            for row in rows:
                counts = (
                    await session.execute(
                        select(
                            func.count(CorpusImportItemRow.id),
                            func.coalesce(func.sum(CorpusImportItemRow.page_count), 0),
                            func.coalesce(func.sum(CorpusImportItemRow.quality_issue_count), 0),
                        ).where(CorpusImportItemRow.batch_id == row.id)
                    )
                ).one()
                results.append(
                    {
                        "id": row.id,
                        "corpus_root_id": row.corpus_root_id,
                        "manifest_sha256": row.manifest_sha256,
                        "status": row.status,
                        "created_by": row.created_by,
                        "created_at": row.created_at,
                        "completed_at": row.completed_at,
                        "item_count": int(counts[0]),
                        "page_count": int(counts[1]),
                        "quality_issue_count": int(counts[2]),
                    }
                )
        return results

    async def list_items(self, batch_id: str) -> list[dict]:
        statement = select(CorpusImportItemRow).where(CorpusImportItemRow.batch_id == batch_id).order_by(CorpusImportItemRow.imported_at.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [
            {
                "id": row.id,
                "batch_id": row.batch_id,
                "bundle_id": row.bundle_id,
                "document_id": row.document_id,
                "source_file_id": row.source_file_id,
                "chunk_set_id": row.chunk_set_id,
                "page_count": row.page_count,
                "quality_issue_count": row.quality_issue_count,
                "status": row.status,
                "imported_by": row.imported_by,
                "imported_at": row.imported_at,
                "error_code": row.error_code,
                "error_message": row.error_message,
            }
            for row in rows
        ]

    async def list_quality_issues(self, item_id: str, *, limit: int, offset: int) -> list[dict]:
        statement = select(CorpusQualityIssueRow).where(CorpusQualityIssueRow.import_item_id == item_id).order_by(CorpusQualityIssueRow.physical_page_number.asc(), CorpusQualityIssueRow.id.asc()).limit(limit).offset(offset)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [
            {
                "id": row.id,
                "import_item_id": row.import_item_id,
                "bundle_id": row.bundle_id,
                "source_file_id": row.source_file_id,
                "code": row.code,
                "severity": row.severity,
                "field": row.field,
                "count": row.count,
                "physical_page_number": row.physical_page_number,
                "folio_label": row.folio_label,
                "message": row.message,
            }
            for row in rows
        ]

    @staticmethod
    async def _add_bundle_rows(session: AsyncSession, imported: CorpusImportBundle) -> None:
        if await session.get(SourceDocumentRow, imported.document.id) is not None:
            raise ValueError("corpus bundle document already exists outside this manifest batch")
        session.add(ObjectMetadataRow(**imported.object_metadata.model_dump(mode="python")))
        session.add(SqlSourceDocumentRepository._document_to_row(imported.document))
        session.add(SourceFileRow(**imported.source_file.model_dump(mode="python")))
        await session.flush()

        session.add(SqlIngestionJobRepository._job_to_row(imported.ingestion_job))
        await session.flush()
        session.add_all(SqlIngestionJobRepository._step_to_row(imported.ingestion_job.id, step, sequence) for sequence, step in enumerate(imported.ingestion_job.steps))
        session.add_all(SqlIngestionJobRepository._event_to_row(event) for event in imported.ingestion_events)

        attempt_rows = []
        for attempt in imported.ocr_attempts:
            values = attempt.model_dump(mode="python", exclude={"regions", "languages"})
            values["status"] = attempt.status.value
            values["languages_json"] = json.dumps(attempt.languages, ensure_ascii=False)
            attempt_rows.append(OcrPageAttemptRow(**values))
        session.add_all(attempt_rows)
        await session.flush()

        session.add_all(
            CleanedOcrPageRow(
                id=page.id,
                source_file_id=page.source_file_id,
                ocr_attempt_id=page.ocr_attempt_id,
                page_number=page.page_number,
                generation_number=page.generation_number,
                raw_text=page.raw_text,
                raw_sha256=page.raw_sha256,
                clean_text=page.clean_text,
                clean_sha256=page.clean_sha256,
                rule_version=page.rule_version,
                script_conversion=page.script_conversion,
                policy_json=page.policy.model_dump_json(),
                generated_by=page.generated_by,
                generated_at=page.generated_at,
            )
            for page in imported.cleaned_pages
        )
        session.add(
            ChunkSetRow(
                id=imported.chunk_set.id,
                document_id=imported.chunk_set.document_id,
                source_file_id=imported.chunk_set.source_file_id,
                split_version=imported.chunk_set.policy.split_version,
                policy_json=imported.chunk_set.policy.model_dump_json(),
                structure_json=json.dumps(
                    [node.model_dump(mode="json") for node in imported.chunk_set.structure],
                    ensure_ascii=False,
                ),
                input_sha256=imported.chunk_set.input_sha256,
                generated_by=imported.chunk_set.generated_by,
                generated_at=imported.chunk_set.generated_at,
            )
        )
        await session.flush()
        session.add_all(
            TextChunkRow(
                id=chunk.id,
                document_id=chunk.document_id,
                source_file_id=chunk.source_file_id,
                chunk_set_id=imported.chunk_set.id,
                split_version=chunk.split_version,
                chunk_index=chunk.chunk_index,
                volume=chunk.volume,
                section=chunk.item,
                item=chunk.item,
                paragraph=str(chunk.paragraph_index),
                paragraph_index=chunk.paragraph_index,
                paragraph_char_start=chunk.paragraph_char_start,
                paragraph_char_end=chunk.paragraph_char_end,
                original_text=chunk.raw_text,
                normalized_text=chunk.clean_text,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                cleaned_page_ids_json=json.dumps(chunk.cleaned_page_ids, ensure_ascii=False),
                content_sha256=chunk.content_sha256,
                review_status="pending",
            )
            for chunk in imported.chunk_set.chunks
        )


def _quality_issue_id(item_id: str, code: str, field: str, page_number: int) -> str:
    digest = hashlib.sha256(f"{item_id}\0{code}\0{field}\0{page_number}".encode()).hexdigest()
    return f"quality-{digest}"
