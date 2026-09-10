"""SQLAlchemy-backed repository for Wu-culture evidence records."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import UTC, timedelta
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from wu_culture import (
    AuthorizationStatus,
    AuthorizedUse,
    Citation,
    CopyrightStatus,
    EntityType,
    Evidence,
    EvidenceRecord,
    ReviewStatus,
    SourceAuthorizationEvent,
    SourceDocument,
    SourceDocumentLibraryFile,
    SourceDocumentLibraryItem,
    SourceDocumentStatus,
    SourceFile,
    SourceLevel,
    SourceType,
    TextChunk,
    VisibilityScope,
    evaluate_source_access,
)
from wu_culture.aliases import AliasIndexError, AliasRecord, AliasType
from wu_culture.chunking import ChunkingPolicy, ChunkSet, StructuredChunk, StructureNode
from wu_culture.cleaning import CleanedOcrPage, TextChange, TextCleaningPolicy
from wu_culture.extraction import is_non_historical_text
from wu_culture.filters import Dynasty, StructuredSearchFilters
from wu_culture.fulltext import (
    FullTextIndexDocument,
    FullTextIndexResult,
    FullTextReleaseNotIndexed,
    FullTextSearchHit,
    FullTextSearchRequest,
    FullTextSearchResponse,
    build_highlighted_snippet,
    parse_fulltext_query,
    score_fulltext_match,
)
from wu_culture.ingestion import (
    IngestionConcurrencyError,
    IngestionEvent,
    IngestionIdempotencyConflict,
    IngestionJob,
    IngestionJobStatus,
    IngestionStep,
    IngestionStepName,
    IngestionStepStatus,
    begin_step,
    recover_interrupted_job,
)
from wu_culture.ocr import OcrBoundingBox, OcrPageAttempt, OcrPageStatus, OcrRegion
from wu_culture.parsing import ParsedBlock, ParsedDocument
from wu_culture.releases import (
    ActivateReleaseRequest,
    KnowledgeRelease,
    KnowledgeReleaseConflict,
    KnowledgeReleaseEvent,
    KnowledgeReleaseGateError,
    KnowledgeReleaseItem,
    KnowledgeReleaseNotFound,
    KnowledgeReleasePreparationError,
    KnowledgeReleaseState,
    PublishReleaseRequest,
    ReleaseAction,
    ReleaseStatus,
    RetryReleaseRequest,
    RollbackReleaseRequest,
    build_knowledge_release,
)
from wu_culture.repositories import DuplicateSourceFileError
from wu_culture.review import (
    PublicationGateDecision,
    ReviewBatchRequest,
    ReviewChunkTarget,
    ReviewConflictError,
    ReviewPageTarget,
    ReviewQueue,
    ReviewRecord,
    ReviewTargetNotFound,
    ReviewTargetType,
    build_review_record,
    evaluate_publication_gate,
)
from wu_culture.storage import ObjectKind, StoredObject
from wu_culture.vectors import (
    VectorBuildItem,
    VectorIndexConflict,
    VectorIndexNotReady,
    VectorIndexState,
    VectorIndexStatus,
    VectorIndexVersion,
    VectorSearchHit,
    VectorSearchRequest,
    VectorSearchResponse,
)

from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture.model import (
    AliasDynastyRow,
    AliasEvidenceRow,
    AliasIndexRow,
    ChunkSetRow,
    CleanedOcrPageRow,
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
    OcrRegionRow,
    ParsedBlockRow,
    ParsedDocumentRow,
    ReviewRecordRow,
    SearchFilterFacetRow,
    SearchFilterMetadataRow,
    SourceAuthorizationEventRow,
    SourceDocumentRow,
    SourceFileRow,
    TextChunkRow,
    TextCleaningChangeRow,
    VectorEmbeddingRow,
    VectorIndexStateRow,
    VectorIndexVersionRow,
)


def _with_utc(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


@lru_cache(maxsize=2)
def _opencc_converter(config: str):
    from opencc import OpenCC

    return OpenCC(config)


@lru_cache(maxsize=4096)
def _script_variants(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                value,
                _opencc_converter("s2t").convert(value),
                _opencc_converter("t2s").convert(value),
            )
        )
    )


def _score_script_variant_match(
    *,
    title: str,
    headings: str,
    body: str,
    phrase_groups: tuple[tuple[str, ...], ...],
    term_groups: tuple[tuple[str, ...], ...],
) -> float:
    phrase_score = sum(max(score_fulltext_match(title=title, headings=headings, body=body, phrases=(variant,), terms=()) for variant in variants) for variants in phrase_groups)
    term_score = sum(max(score_fulltext_match(title=title, headings=headings, body=body, phrases=(), terms=(variant,)) for variant in variants) for variants in term_groups)
    return round(phrase_score + term_score, 6)


async def _load_chunk_folio_ranges(
    session: AsyncSession,
    chunk_ids: tuple[str, ...],
) -> dict[str, tuple[str | None, str | None]]:
    if not chunk_ids:
        return {}
    chunks = list((await session.execute(select(TextChunkRow).where(TextChunkRow.id.in_(chunk_ids)))).scalars().all())
    page_ids = tuple(dict.fromkeys(page_id for chunk in chunks for page_id in json.loads(chunk.cleaned_page_ids_json)))
    if not page_ids:
        return {chunk.id: (None, None) for chunk in chunks}
    folio_by_page_id = {
        page_id: folio_label
        for page_id, folio_label in (
            await session.execute(
                select(CleanedOcrPageRow.id, OcrPageAttemptRow.folio_label)
                .join(
                    OcrPageAttemptRow,
                    CleanedOcrPageRow.ocr_attempt_id == OcrPageAttemptRow.id,
                )
                .where(CleanedOcrPageRow.id.in_(page_ids))
            )
        ).all()
        if folio_label is not None
    }
    result = {}
    for chunk in chunks:
        labels = tuple(folio_by_page_id[page_id] for page_id in json.loads(chunk.cleaned_page_ids_json) if page_id in folio_by_page_id)
        result[chunk.id] = (
            labels[0] if labels else None,
            labels[-1] if labels else None,
        )
    return result


class SqlAliasRepository:
    """Persist immutable Release-scoped alias candidates and evidence bindings."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def replace_release(self, release_id: str, records: tuple[AliasRecord, ...]) -> None:
        if any(record.release_id != release_id for record in records):
            raise AliasIndexError("all alias records must belong to the replaced Release")
        evidence_ids = {evidence_id for record in records for evidence_id in record.evidence_ids}
        async with self._session_factory() as session:
            if await session.get(KnowledgeReleaseRow, release_id) is None:
                raise AliasIndexError(f"knowledge release {release_id!r} was not found")
            if evidence_ids:
                existing_evidence = set((await session.execute(select(EvidenceRow.id).where(EvidenceRow.id.in_(tuple(evidence_ids))))).scalars().all())
                missing = evidence_ids - existing_evidence
                if missing:
                    raise AliasIndexError(f"alias evidence was not found: {', '.join(sorted(missing))}")
            existing_alias_ids = tuple((await session.execute(select(AliasIndexRow.id).where(AliasIndexRow.release_id == release_id))).scalars().all())
            if existing_alias_ids:
                await session.execute(delete(AliasEvidenceRow).where(AliasEvidenceRow.alias_id.in_(existing_alias_ids)))
                await session.execute(delete(AliasDynastyRow).where(AliasDynastyRow.alias_id.in_(existing_alias_ids)))
                await session.execute(delete(AliasIndexRow).where(AliasIndexRow.id.in_(existing_alias_ids)))
            session.add_all(
                AliasIndexRow(
                    id=record.id,
                    release_id=record.release_id,
                    entity_id=record.entity_id,
                    canonical_name=record.canonical_name,
                    entity_type=record.entity_type.value,
                    alias=record.alias,
                    normalized_alias=self._normalize(record.alias),
                    alias_length=len(self._normalize(record.alias)),
                    alias_type=record.alias_type.value,
                    review_status=record.review_status.value,
                    indexed_at=record.indexed_at,
                )
                for record in records
            )
            await session.flush()
            session.add_all(AliasDynastyRow(alias_id=record.id, dynasty=dynasty.value) for record in records for dynasty in record.applicable_dynasties)
            session.add_all(AliasEvidenceRow(alias_id=record.id, evidence_id=evidence_id) for record in records for evidence_id in record.evidence_ids)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise AliasIndexError("alias index violates a uniqueness or evidence constraint") from exc

    async def list_matching(self, release_id: str, query: str) -> tuple[AliasRecord, ...]:
        normalized_query = self._normalize(query)
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(AliasIndexRow).where(AliasIndexRow.release_id == release_id).order_by(AliasIndexRow.alias_length.desc(), AliasIndexRow.normalized_alias.asc(), AliasIndexRow.entity_id.asc(), AliasIndexRow.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            rows = [row for row in rows if row.normalized_alias in normalized_query][:50]
            alias_ids = tuple(row.id for row in rows)
            dynasties: dict[str, list[Dynasty]] = {}
            evidence: dict[str, list[str]] = {}
            if alias_ids:
                for alias_id, dynasty in (await session.execute(select(AliasDynastyRow.alias_id, AliasDynastyRow.dynasty).where(AliasDynastyRow.alias_id.in_(alias_ids)))).all():
                    dynasties.setdefault(alias_id, []).append(Dynasty(dynasty))
                for alias_id, evidence_id in (await session.execute(select(AliasEvidenceRow.alias_id, AliasEvidenceRow.evidence_id).where(AliasEvidenceRow.alias_id.in_(alias_ids)))).all():
                    evidence.setdefault(alias_id, []).append(evidence_id)
        return tuple(
            AliasRecord(
                id=row.id,
                release_id=row.release_id,
                entity_id=row.entity_id,
                canonical_name=row.canonical_name,
                entity_type=EntityType(row.entity_type),
                alias=row.alias,
                alias_type=AliasType(row.alias_type),
                applicable_dynasties=tuple(sorted(dynasties.get(row.id, []), key=lambda value: value.value)),
                evidence_ids=tuple(sorted(evidence.get(row.id, []))),
                review_status=ReviewStatus(row.review_status),
                indexed_at=_with_utc(row.indexed_at),
            )
            for row in rows
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return unicodedata.normalize("NFKC", value).casefold().strip()


def _apply_structured_search_filters(statement, filters: StructuredSearchFilters):  # noqa: ANN001, ANN202
    if filters.document_ids:
        statement = statement.where(SearchFilterMetadataRow.document_id.in_(filters.document_ids))
    if filters.editions:
        statement = statement.where(SearchFilterMetadataRow.edition.in_(filters.editions))
    if filters.source_types:
        statement = statement.where(SearchFilterMetadataRow.source_type.in_(tuple(value.value for value in filters.source_types)))
    if filters.source_levels:
        statement = statement.where(SearchFilterMetadataRow.source_level.in_(tuple(value.value for value in filters.source_levels)))
    if filters.review_statuses:
        statement = statement.where(SearchFilterMetadataRow.review_status.in_(tuple(value.value for value in filters.review_statuses)))
    if filters.min_spatial_confidence is not None:
        statement = statement.where(SearchFilterMetadataRow.spatial_confidence >= filters.min_spatial_confidence)
    if filters.max_spatial_confidence is not None:
        statement = statement.where(SearchFilterMetadataRow.spatial_confidence <= filters.max_spatial_confidence)
    for facet_type, values in (
        ("dynasty", filters.dynasties),
        ("entity_type", filters.entity_types),
    ):
        if values:
            facet_values = tuple(value.value for value in values)
            facet_exists = (
                select(SearchFilterFacetRow.release_id)
                .where(
                    SearchFilterFacetRow.release_id == SearchFilterMetadataRow.release_id,
                    SearchFilterFacetRow.chunk_id == SearchFilterMetadataRow.chunk_id,
                    SearchFilterFacetRow.facet_type == facet_type,
                    SearchFilterFacetRow.facet_value.in_(facet_values),
                )
                .exists()
            )
            statement = statement.where(facet_exists)
    return statement


class SqlSourceDocumentRepository:
    """Create and maintain registered historical-source metadata."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, document: SourceDocument) -> SourceDocument:
        async with self._session_factory() as session:
            session.add(self._document_to_row(document))
            await session.commit()
        return document

    async def get(self, document_id: str) -> SourceDocument | None:
        async with self._session_factory() as session:
            row = await session.get(SourceDocumentRow, document_id)
        return self._row_to_document(row) if row is not None else None

    async def list(self) -> list[SourceDocument]:
        statement = select(SourceDocumentRow).order_by(SourceDocumentRow.created_at.asc(), SourceDocumentRow.id.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [self._row_to_document(row) for row in rows]

    async def list_page(
        self,
        *,
        query: str | None = None,
        status: SourceDocumentStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SourceDocument], int]:
        filters = []
        if query:
            needle = f"%{query.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(SourceDocumentRow.title).like(needle),
                    func.lower(SourceDocumentRow.edition).like(needle),
                    func.lower(SourceDocumentRow.source_institution).like(needle),
                )
            )
        if status is not None:
            filters.append(SourceDocumentRow.status == status.value)
        count_statement = select(func.count()).select_from(SourceDocumentRow).where(*filters)
        statement = select(SourceDocumentRow).where(*filters).order_by(SourceDocumentRow.updated_at.desc(), SourceDocumentRow.id.asc()).limit(limit).offset(offset)
        async with self._session_factory() as session:
            total = int((await session.execute(count_statement)).scalar_one())
            rows = (await session.execute(statement)).scalars().all()
        return [self._row_to_document(row) for row in rows], total

    async def list_library_page(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SourceDocumentLibraryItem], int]:
        """Read a source page with files and latest ingestion jobs in batches."""
        filters = []
        if query:
            needle = f"%{query.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(SourceDocumentRow.title).like(needle),
                    func.lower(SourceDocumentRow.edition).like(needle),
                    func.lower(SourceDocumentRow.source_institution).like(needle),
                )
            )
        if status:
            filters.append(SourceDocumentRow.status == status)

        count_statement = select(func.count()).select_from(SourceDocumentRow).where(*filters)
        source_page = select(SourceDocumentRow.id).where(*filters).order_by(SourceDocumentRow.updated_at.desc(), SourceDocumentRow.id.asc()).limit(limit).offset(offset).subquery()
        latest_job_id = select(IngestionJobRow.id).where(IngestionJobRow.source_file_id == SourceFileRow.id).order_by(IngestionJobRow.created_at.desc(), IngestionJobRow.id.desc()).limit(1).correlate(SourceFileRow).scalar_subquery()
        library_statement = (
            select(SourceDocumentRow, SourceFileRow, IngestionJobRow)
            .join(source_page, source_page.c.id == SourceDocumentRow.id)
            .outerjoin(SourceFileRow, SourceFileRow.document_id == SourceDocumentRow.id)
            .outerjoin(IngestionJobRow, IngestionJobRow.id == latest_job_id)
            .order_by(
                SourceDocumentRow.updated_at.desc(),
                SourceDocumentRow.id.asc(),
                SourceFileRow.uploaded_at.asc(),
                SourceFileRow.id.asc(),
            )
        )

        async with self._session_factory() as session:
            total = int((await session.execute(count_statement)).scalar_one())
            rows = (await session.execute(library_statement)).all()
            job_ids = tuple({job_row.id for _, _, job_row in rows if job_row is not None})
            steps_by_job: dict[str, list[IngestionStepRow]] = {}
            if job_ids:
                step_statement = select(IngestionStepRow).where(IngestionStepRow.job_id.in_(job_ids)).order_by(IngestionStepRow.job_id.asc(), IngestionStepRow.sequence.asc())
                for step_row in (await session.execute(step_statement)).scalars().all():
                    steps_by_job.setdefault(step_row.job_id, []).append(step_row)

        jobs = {job_row.id: SqlIngestionJobRepository._row_to_job_from_steps(job_row, steps_by_job.get(job_row.id, ())) for _, _, job_row in rows if job_row is not None}
        documents: dict[str, SourceDocument] = {}
        files: dict[str, list[SourceDocumentLibraryFile]] = {}
        for document_row, file_row, job_row in rows:
            document = documents.setdefault(document_row.id, self._row_to_document(document_row))
            files.setdefault(document.id, [])
            if file_row is not None:
                files[document.id].append(
                    SourceDocumentLibraryFile(
                        file=SqlSourceFileRepository._row_to_domain(file_row),
                        ingestion_job=jobs.get(job_row.id) if job_row is not None else None,
                    )
                )
        return [SourceDocumentLibraryItem(document=document, files=tuple(files[document.id])) for document in documents.values()], total

    async def update(self, document: SourceDocument) -> SourceDocument | None:
        async with self._session_factory() as session:
            row = await session.get(SourceDocumentRow, document.id)
            if row is None:
                return None
            values = self._document_values(document)
            for name, value in values.items():
                setattr(row, name, value)
            await session.commit()
        return document

    async def update_authorization(
        self,
        document: SourceDocument,
        event: SourceAuthorizationEvent,
    ) -> SourceDocument | None:
        async with self._session_factory() as session:
            row = await session.get(SourceDocumentRow, document.id)
            if row is None:
                return None
            for name, value in self._document_values(document).items():
                setattr(row, name, value)
            session.add(self._authorization_event_to_row(event))
            await session.commit()
        return document

    async def list_authorization_events(self, document_id: str) -> list[SourceAuthorizationEvent]:
        statement = select(SourceAuthorizationEventRow).where(SourceAuthorizationEventRow.document_id == document_id).order_by(SourceAuthorizationEventRow.changed_at.asc(), SourceAuthorizationEventRow.id.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [self._authorization_event_to_domain(row) for row in rows]

    @staticmethod
    def _document_values(document: SourceDocument) -> dict:
        return {
            "id": document.id,
            "title": document.title,
            "edition": document.edition,
            "source_type": document.source_type.value,
            "source_type_label": document.source_type_label,
            "source_level": document.source_level.value,
            "copyright_status": document.copyright_status.value,
            "source_institution": document.source_institution,
            "holder": document.holder,
            "status": document.status.value,
            "authorization_status": document.authorization_status.value,
            "authorization_basis": document.authorization_basis,
            "authorization_valid_from": document.authorization_valid_from,
            "authorization_valid_until": document.authorization_valid_until,
            "visibility_scope": document.visibility_scope.value,
            "authorized_uses_json": json.dumps([use.value for use in document.authorized_uses]),
            "authorization_proof_object_key": document.authorization_proof_object_key,
            "file_hash": document.file_hash,
            "created_by": document.created_by,
            "created_at": document.created_at,
            "updated_by": document.updated_by,
            "updated_at": document.updated_at,
        }

    @classmethod
    def _document_to_row(cls, document: SourceDocument) -> SourceDocumentRow:
        return SourceDocumentRow(**cls._document_values(document))

    @staticmethod
    def _row_to_document(row: SourceDocumentRow) -> SourceDocument:
        return SourceDocument(
            id=row.id,
            title=row.title,
            edition=row.edition,
            source_type=SourceType(row.source_type),
            source_type_label=row.source_type_label,
            source_level=SourceLevel(row.source_level),
            copyright_status=CopyrightStatus(row.copyright_status),
            source_institution=row.source_institution,
            holder=row.holder,
            status=SourceDocumentStatus(row.status),
            authorization_status=AuthorizationStatus(row.authorization_status),
            authorization_basis=row.authorization_basis,
            authorization_valid_from=_with_utc(row.authorization_valid_from),
            authorization_valid_until=_with_utc(row.authorization_valid_until),
            visibility_scope=VisibilityScope(row.visibility_scope),
            authorized_uses=tuple(AuthorizedUse(use) for use in json.loads(row.authorized_uses_json)),
            authorization_proof_object_key=row.authorization_proof_object_key,
            file_hash=row.file_hash,
            created_by=row.created_by,
            created_at=_with_utc(row.created_at),
            updated_by=row.updated_by,
            updated_at=_with_utc(row.updated_at),
        )

    @staticmethod
    def _authorization_event_to_row(event: SourceAuthorizationEvent) -> SourceAuthorizationEventRow:
        return SourceAuthorizationEventRow(
            id=event.id,
            document_id=event.document_id,
            previous_status=event.previous_status.value,
            new_status=event.new_status.value,
            previous_copyright_status=event.previous_copyright_status.value,
            new_copyright_status=event.new_copyright_status.value,
            new_visibility_scope=event.new_visibility_scope.value,
            new_authorized_uses_json=json.dumps([use.value for use in event.new_authorized_uses]),
            authorization_valid_until=event.authorization_valid_until,
            authorization_proof_object_key=event.authorization_proof_object_key,
            changed_by=event.changed_by,
            changed_at=event.changed_at,
            reason=event.reason,
        )

    @staticmethod
    def _authorization_event_to_domain(row: SourceAuthorizationEventRow) -> SourceAuthorizationEvent:
        return SourceAuthorizationEvent(
            id=row.id,
            document_id=row.document_id,
            previous_status=AuthorizationStatus(row.previous_status),
            new_status=AuthorizationStatus(row.new_status),
            previous_copyright_status=CopyrightStatus(row.previous_copyright_status),
            new_copyright_status=CopyrightStatus(row.new_copyright_status),
            new_visibility_scope=VisibilityScope(row.new_visibility_scope),
            new_authorized_uses=tuple(AuthorizedUse(use) for use in json.loads(row.new_authorized_uses_json)),
            authorization_valid_until=_with_utc(row.authorization_valid_until),
            authorization_proof_object_key=row.authorization_proof_object_key,
            changed_by=row.changed_by,
            changed_at=_with_utc(row.changed_at),
            reason=row.reason,
        )


class SqlSourceFileRepository:
    """Atomically bind stored-object metadata to a registered source."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def attach(self, source_file: SourceFile, metadata: StoredObject) -> SourceFile:
        async with self._session_factory() as session:
            try:
                existing = await session.get(ObjectMetadataRow, metadata.object_key)
                if existing is None:
                    session.add(ObjectMetadataRow(**metadata.model_dump(mode="python")))
                elif self._metadata_to_domain(existing) != metadata:
                    raise ValueError(f"Conflicting metadata for object_key {metadata.object_key!r}")
                session.add(SourceFileRow(**source_file.model_dump(mode="python")))
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                existing_file = await self.find_by_sha256(metadata.sha256)
                if existing_file is not None and source_file.duplicate_of_file_id is None:
                    raise DuplicateSourceFileError(existing_file) from exc
                raise
            except Exception:
                await session.rollback()
                raise
        return source_file

    async def list_for_document(self, document_id: str) -> list[SourceFile]:
        statement = select(SourceFileRow).where(SourceFileRow.document_id == document_id).order_by(SourceFileRow.uploaded_at.asc(), SourceFileRow.id.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [self._row_to_domain(row) for row in rows]

    async def list_all(self) -> list[SourceFile]:
        statement = select(SourceFileRow).order_by(SourceFileRow.uploaded_at.asc(), SourceFileRow.id.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [self._row_to_domain(row) for row in rows]

    async def find_by_sha256(self, sha256: str) -> SourceFile | None:
        statement = select(SourceFileRow).join(ObjectMetadataRow, SourceFileRow.object_key == ObjectMetadataRow.object_key).where(ObjectMetadataRow.sha256 == sha256).order_by(SourceFileRow.uploaded_at.asc(), SourceFileRow.id.asc()).limit(1)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        return self._row_to_domain(row) if row is not None else None

    async def get(self, file_id: str) -> SourceFile | None:
        async with self._session_factory() as session:
            row = await session.get(SourceFileRow, file_id)
        return self._row_to_domain(row) if row is not None else None

    async def find_by_document_and_filename(self, document_id: str, filename: str) -> SourceFile | None:
        statement = (
            select(SourceFileRow)
            .where(
                SourceFileRow.document_id == document_id,
                SourceFileRow.original_filename == filename,
            )
            .order_by(SourceFileRow.uploaded_at.desc(), SourceFileRow.id.desc())
            .limit(1)
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        return self._row_to_domain(row) if row is not None else None

    @staticmethod
    def _metadata_to_domain(row: ObjectMetadataRow) -> StoredObject:
        return StoredObject(
            object_key=row.object_key,
            owner_id=row.owner_id,
            kind=ObjectKind(row.kind),
            sha256=row.sha256,
            mime_type=row.mime_type,
            size=row.size,
            backend=row.backend,
            storage_uri=row.storage_uri,
            original_filename=row.original_filename,
            created_at=_with_utc(row.created_at),
        )

    @staticmethod
    def _row_to_domain(row: SourceFileRow) -> SourceFile:
        return SourceFile(
            id=row.id,
            document_id=row.document_id,
            object_key=row.object_key,
            original_filename=row.original_filename,
            mime_type=row.mime_type,
            size=row.size,
            sha256=row.sha256,
            duplicate_of_file_id=row.duplicate_of_file_id,
            version_of_file_id=row.version_of_file_id,
            uploaded_by=row.uploaded_by,
            uploaded_at=_with_utc(row.uploaded_at),
        )


class SqlParsedDocumentRepository:
    """Persist one structured digital parse for each canonical source file."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, document: ParsedDocument) -> ParsedDocument:
        async with self._session_factory() as session:
            session.add(
                ParsedDocumentRow(
                    id=document.id,
                    source_file_id=document.source_file_id,
                    parser_name=document.parser_name,
                    parser_version=document.parser_version,
                    mime_type=document.mime_type,
                    page_count=document.page_count,
                    text=document.text,
                    metadata_json=json.dumps(document.metadata, ensure_ascii=False),
                    parsed_at=document.parsed_at,
                )
            )
            # Parsed blocks reference the parent row. Flush the parent first so
            # SQLite/Postgres enforce the same foreign-key ordering.
            await session.flush()
            session.add_all(
                [
                    ParsedBlockRow(
                        id=f"{document.id}-block-{block.block_index}",
                        parsed_document_id=document.id,
                        block_type=block.block_type,
                        page_number=block.page_number,
                        block_index=block.block_index,
                        text=block.text,
                        metadata_json=json.dumps(block.metadata, ensure_ascii=False),
                    )
                    for block in document.blocks
                ]
            )
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return document

    async def get_by_source_file_id(self, source_file_id: str) -> ParsedDocument | None:
        statement = select(ParsedDocumentRow).where(ParsedDocumentRow.source_file_id == source_file_id)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
            if row is None:
                return None
            block_statement = select(ParsedBlockRow).where(ParsedBlockRow.parsed_document_id == row.id).order_by(ParsedBlockRow.block_index.asc())
            block_rows = (await session.execute(block_statement)).scalars().all()
        return ParsedDocument(
            id=row.id,
            source_file_id=row.source_file_id,
            parser_name=row.parser_name,
            parser_version=row.parser_version,
            mime_type=row.mime_type,
            page_count=row.page_count,
            text=row.text,
            metadata=json.loads(row.metadata_json),
            parsed_at=_with_utc(row.parsed_at),
            blocks=tuple(
                ParsedBlock(
                    block_type=block.block_type,
                    page_number=block.page_number,
                    block_index=block.block_index,
                    text=block.text,
                    metadata=json.loads(block.metadata_json),
                )
                for block in block_rows
            ),
        )


class SqlOcrRepository:
    """Append OCR attempts and query page-level latest results."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_attempts(self, attempts: Sequence[OcrPageAttempt]) -> None:
        async with self._session_factory() as session:
            for attempt in attempts:
                session.add(self._attempt_to_row(attempt))
                session.add_all(self._region_to_row(attempt, index, region) for index, region in enumerate(attempt.regions))
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def list_attempts(self, source_file_id: str, *, page_number: int | None = None) -> list[OcrPageAttempt]:
        statement = select(OcrPageAttemptRow).where(OcrPageAttemptRow.source_file_id == source_file_id)
        if page_number is not None:
            statement = statement.where(OcrPageAttemptRow.page_number == page_number)
        statement = statement.order_by(OcrPageAttemptRow.page_number.asc(), OcrPageAttemptRow.attempt_number.asc())
        return await self._load(statement)

    async def list_latest(self, source_file_id: str) -> list[OcrPageAttempt]:
        latest = select(OcrPageAttemptRow.page_number, func.max(OcrPageAttemptRow.attempt_number).label("attempt_number")).where(OcrPageAttemptRow.source_file_id == source_file_id).group_by(OcrPageAttemptRow.page_number).subquery()
        statement = (
            select(OcrPageAttemptRow)
            .join(latest, (OcrPageAttemptRow.page_number == latest.c.page_number) & (OcrPageAttemptRow.attempt_number == latest.c.attempt_number))
            .where(OcrPageAttemptRow.source_file_id == source_file_id)
            .order_by(OcrPageAttemptRow.page_number.asc())
        )
        return await self._load(statement)

    async def list_review_queue(self) -> list[OcrPageAttempt]:
        latest = (
            select(
                OcrPageAttemptRow.source_file_id,
                OcrPageAttemptRow.page_number,
                func.max(OcrPageAttemptRow.attempt_number).label("attempt_number"),
            )
            .group_by(OcrPageAttemptRow.source_file_id, OcrPageAttemptRow.page_number)
            .subquery()
        )
        statement = (
            select(OcrPageAttemptRow)
            .join(
                latest,
                (OcrPageAttemptRow.source_file_id == latest.c.source_file_id) & (OcrPageAttemptRow.page_number == latest.c.page_number) & (OcrPageAttemptRow.attempt_number == latest.c.attempt_number),
            )
            .where(OcrPageAttemptRow.status == OcrPageStatus.REVIEW_REQUIRED.value)
            .order_by(OcrPageAttemptRow.created_at.asc(), OcrPageAttemptRow.source_file_id.asc(), OcrPageAttemptRow.page_number.asc())
        )
        return await self._load(statement)

    async def _load(self, statement) -> list[OcrPageAttempt]:
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
            attempt_ids = [row.id for row in rows]
            regions_by_attempt: dict[str, list[OcrRegionRow]] = {attempt_id: [] for attempt_id in attempt_ids}
            if attempt_ids:
                region_statement = select(OcrRegionRow).where(OcrRegionRow.attempt_id.in_(attempt_ids)).order_by(OcrRegionRow.attempt_id.asc(), OcrRegionRow.region_index.asc())
                for region in (await session.execute(region_statement)).scalars().all():
                    regions_by_attempt[region.attempt_id].append(region)
        return [self._row_to_attempt(row, regions_by_attempt[row.id]) for row in rows]

    @staticmethod
    def _attempt_to_row(attempt: OcrPageAttempt) -> OcrPageAttemptRow:
        values = attempt.model_dump(mode="python", exclude={"regions"})
        values["status"] = attempt.status.value
        values["languages_json"] = json.dumps(attempt.languages, ensure_ascii=False)
        values.pop("languages")
        return OcrPageAttemptRow(**values)

    @staticmethod
    def _region_to_row(attempt: OcrPageAttempt, index: int, region: OcrRegion) -> OcrRegionRow:
        return OcrRegionRow(
            id=f"{attempt.id}-region-{index}",
            attempt_id=attempt.id,
            region_index=index,
            text=region.text,
            confidence=region.confidence,
            **region.bounding_box.model_dump(),
        )

    @staticmethod
    def _row_to_attempt(row: OcrPageAttemptRow, regions: Sequence[OcrRegionRow]) -> OcrPageAttempt:
        return OcrPageAttempt(
            id=row.id,
            source_file_id=row.source_file_id,
            page_number=row.page_number,
            attempt_number=row.attempt_number,
            folio_label=row.folio_label,
            page_image_object_key=row.page_image_object_key,
            image_sha256=row.image_sha256,
            image_width=row.image_width,
            image_height=row.image_height,
            provider_name=row.provider_name,
            model_name=row.model_name,
            languages=tuple(json.loads(row.languages_json)),
            status=OcrPageStatus(row.status),
            raw_text=row.raw_text,
            mean_confidence=row.mean_confidence,
            rotation_degrees=row.rotation_degrees,
            regions=tuple(OcrRegion(text=region.text, confidence=region.confidence, bounding_box=OcrBoundingBox(x=region.x, y=region.y, width=region.width, height=region.height)) for region in regions),
            error_code=row.error_code,
            error_message=row.error_message,
            created_at=_with_utc(row.created_at),
        )


class SqlTextCleaningRepository:
    """Append cleaning generations while retaining raw and every change record."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, page: CleanedOcrPage) -> None:
        await self.save_many((page,))

    async def save_many(self, pages: Sequence[CleanedOcrPage]) -> None:
        async with self._session_factory() as session:
            for page in pages:
                session.add(
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
                )
                session.add_all(
                    TextCleaningChangeRow(
                        id=f"{page.id}-change-{change.sequence}",
                        cleaned_page_id=page.id,
                        **change.model_dump(),
                    )
                    for change in page.changes
                )
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def list_generations(self, ocr_attempt_id: str) -> list[CleanedOcrPage]:
        statement = select(CleanedOcrPageRow).where(CleanedOcrPageRow.ocr_attempt_id == ocr_attempt_id).order_by(CleanedOcrPageRow.generation_number.asc())
        return await self._load(statement)

    async def list_latest(self, source_file_id: str) -> list[CleanedOcrPage]:
        latest = select(CleanedOcrPageRow.page_number, func.max(CleanedOcrPageRow.generation_number).label("generation_number")).where(CleanedOcrPageRow.source_file_id == source_file_id).group_by(CleanedOcrPageRow.page_number).subquery()
        statement = (
            select(CleanedOcrPageRow)
            .join(
                latest,
                (CleanedOcrPageRow.page_number == latest.c.page_number) & (CleanedOcrPageRow.generation_number == latest.c.generation_number),
            )
            .where(CleanedOcrPageRow.source_file_id == source_file_id)
            .order_by(CleanedOcrPageRow.page_number.asc())
        )
        return await self._load(statement)

    async def list_page_generations(self, source_file_id: str, page_number: int) -> list[CleanedOcrPage]:
        statement = select(CleanedOcrPageRow).where(CleanedOcrPageRow.source_file_id == source_file_id, CleanedOcrPageRow.page_number == page_number).order_by(CleanedOcrPageRow.generation_number.asc())
        return await self._load(statement)

    async def _load(self, statement) -> list[CleanedOcrPage]:
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
            ids = [row.id for row in rows]
            changes_by_page: dict[str, list[TextCleaningChangeRow]] = {row_id: [] for row_id in ids}
            if ids:
                change_statement = select(TextCleaningChangeRow).where(TextCleaningChangeRow.cleaned_page_id.in_(ids)).order_by(TextCleaningChangeRow.cleaned_page_id.asc(), TextCleaningChangeRow.sequence.asc())
                for change in (await session.execute(change_statement)).scalars().all():
                    changes_by_page[change.cleaned_page_id].append(change)
        return [self._row_to_page(row, changes_by_page[row.id]) for row in rows]

    @staticmethod
    def _row_to_page(row: CleanedOcrPageRow, changes: Sequence[TextCleaningChangeRow]) -> CleanedOcrPage:
        return CleanedOcrPage(
            id=row.id,
            source_file_id=row.source_file_id,
            ocr_attempt_id=row.ocr_attempt_id,
            page_number=row.page_number,
            generation_number=row.generation_number,
            raw_text=row.raw_text,
            raw_sha256=row.raw_sha256,
            clean_text=row.clean_text,
            clean_sha256=row.clean_sha256,
            rule_version=row.rule_version,
            script_conversion=row.script_conversion,
            policy=TextCleaningPolicy.model_validate_json(row.policy_json),
            changes=tuple(
                TextChange(
                    sequence=change.sequence,
                    rule_id=change.rule_id,
                    raw_start=change.raw_start,
                    raw_end=change.raw_end,
                    clean_start=change.clean_start,
                    clean_end=change.clean_end,
                    before=change.before,
                    after=change.after,
                )
                for change in changes
            ),
            generated_by=row.generated_by,
            generated_at=_with_utc(row.generated_at),
        )


class SqlStructuredChunkRepository:
    """Persist immutable, versioned structure trees and their stable chunks."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, chunk_set: ChunkSet) -> None:
        async with self._session_factory() as session:
            session.add(
                ChunkSetRow(
                    id=chunk_set.id,
                    document_id=chunk_set.document_id,
                    source_file_id=chunk_set.source_file_id,
                    split_version=chunk_set.policy.split_version,
                    policy_json=chunk_set.policy.model_dump_json(),
                    structure_json=json.dumps([node.model_dump(mode="json") for node in chunk_set.structure], ensure_ascii=False),
                    input_sha256=chunk_set.input_sha256,
                    generated_by=chunk_set.generated_by,
                    generated_at=chunk_set.generated_at,
                )
            )
            session.add_all(
                TextChunkRow(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    source_file_id=chunk.source_file_id,
                    chunk_set_id=chunk_set.id,
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
                    review_status=ReviewStatus.PENDING.value,
                )
                for chunk in chunk_set.chunks
            )
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get(self, source_file_id: str, split_version: str) -> ChunkSet | None:
        statement = select(ChunkSetRow).where(ChunkSetRow.source_file_id == source_file_id, ChunkSetRow.split_version == split_version)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
            if row is None:
                return None
            chunks = await self._load_chunks(session, row.id)
        return self._row_to_set(row, chunks)

    async def list_versions(self, source_file_id: str) -> list[ChunkSet]:
        statement = select(ChunkSetRow).where(ChunkSetRow.source_file_id == source_file_id).order_by(ChunkSetRow.generated_at.asc(), ChunkSetRow.id.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
            results = []
            for row in rows:
                results.append(self._row_to_set(row, await self._load_chunks(session, row.id)))
        return results

    async def list_all(self) -> list[ChunkSet]:
        """Return every chunk set so a working release cannot omit a document."""
        statement = select(ChunkSetRow).order_by(ChunkSetRow.generated_at.asc(), ChunkSetRow.id.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
            return [self._row_to_set(row, await self._load_chunks(session, row.id)) for row in rows]

    @staticmethod
    async def _load_chunks(session: AsyncSession, chunk_set_id: str) -> list[TextChunkRow]:
        statement = select(TextChunkRow).where(TextChunkRow.chunk_set_id == chunk_set_id).order_by(TextChunkRow.chunk_index.asc())
        return list((await session.execute(statement)).scalars().all())

    @staticmethod
    def _row_to_set(row: ChunkSetRow, chunk_rows: Sequence[TextChunkRow]) -> ChunkSet:
        policy = ChunkingPolicy.model_validate_json(row.policy_json)
        structure = tuple(StructureNode.model_validate(node) for node in json.loads(row.structure_json))
        chunks = tuple(
            StructuredChunk(
                id=chunk.id,
                document_id=chunk.document_id,
                source_file_id=chunk.source_file_id,
                split_version=chunk.split_version,
                chunk_index=chunk.chunk_index,
                volume=chunk.volume,
                item=chunk.item,
                paragraph_index=chunk.paragraph_index,
                paragraph_char_start=chunk.paragraph_char_start,
                paragraph_char_end=chunk.paragraph_char_end,
                raw_text=chunk.original_text,
                clean_text=chunk.normalized_text,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                cleaned_page_ids=tuple(json.loads(chunk.cleaned_page_ids_json)),
                content_sha256=chunk.content_sha256,
            )
            for chunk in chunk_rows
        )
        return ChunkSet(
            id=row.id,
            document_id=row.document_id,
            source_file_id=row.source_file_id,
            policy=policy,
            structure=structure,
            chunks=chunks,
            input_sha256=row.input_sha256,
            generated_by=row.generated_by,
            generated_at=_with_utc(row.generated_at),
        )


class SqlReviewRepository:
    """Append immutable page/chunk reviews and materialize current status."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def review_many(
        self,
        *,
        document_id: str,
        source_file_id: str,
        batch: ReviewBatchRequest,
        reviewed_by: str,
        reviewed_at,
        batch_id: str,
    ) -> list[ReviewRecord]:
        async with self._session_factory() as session:
            source_file = await session.get(SourceFileRow, source_file_id)
            if source_file is None or source_file.document_id != document_id:
                raise ReviewTargetNotFound("source file does not belong to the document")

            targets: list[tuple[object, ReviewStatus]] = []
            for request in batch.items:
                if request.target_type is ReviewTargetType.PAGE:
                    row = await session.get(CleanedOcrPageRow, request.target_id)
                    if row is None or row.source_file_id != source_file_id:
                        raise ReviewTargetNotFound(f"review page {request.target_id!r} was not found in the source file")
                else:
                    row = await session.get(TextChunkRow, request.target_id)
                    if row is None or row.source_file_id != source_file_id or row.document_id != document_id:
                        raise ReviewTargetNotFound(f"review chunk {request.target_id!r} was not found in the source file")
                targets.append((row, ReviewStatus(row.review_status)))

            records: list[ReviewRecord] = []
            for request, (row, previous_status) in zip(batch.items, targets, strict=True):
                revision_statement = select(func.coalesce(func.max(ReviewRecordRow.revision), 0)).where(
                    ReviewRecordRow.target_type == request.target_type.value,
                    ReviewRecordRow.target_id == request.target_id,
                )
                revision = int((await session.execute(revision_statement)).scalar_one()) + 1
                record = build_review_record(
                    record_id=f"review-{uuid4().hex}",
                    document_id=document_id,
                    source_file_id=source_file_id,
                    request=request,
                    previous_status=previous_status,
                    revision=revision,
                    reviewed_by=reviewed_by,
                    reviewed_at=reviewed_at,
                    batch_id=batch_id,
                )
                row.review_status = record.decision.value
                session.add(self._record_to_row(record))
                records.append(record)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ReviewConflictError("review target changed concurrently; reload its latest history") from exc
        return records

    async def list_records(
        self,
        *,
        source_file_id: str,
        target_type: ReviewTargetType | None = None,
        target_id: str | None = None,
    ) -> list[ReviewRecord]:
        statement = select(ReviewRecordRow).where(ReviewRecordRow.source_file_id == source_file_id)
        if target_type is not None:
            statement = statement.where(ReviewRecordRow.target_type == target_type.value)
        if target_id is not None:
            statement = statement.where(ReviewRecordRow.target_id == target_id)
        statement = statement.order_by(ReviewRecordRow.reviewed_at.asc(), ReviewRecordRow.target_type.asc(), ReviewRecordRow.target_id.asc(), ReviewRecordRow.revision.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [self._row_to_record(row) for row in rows]

    async def publication_gate(self, *, source_file_id: str, chunk_id: str) -> PublicationGateDecision:
        async with self._session_factory() as session:
            chunk = await session.get(TextChunkRow, chunk_id)
            if chunk is None or chunk.source_file_id != source_file_id:
                raise ReviewTargetNotFound(f"review chunk {chunk_id!r} was not found in the source file")
            page_ids = tuple(json.loads(chunk.cleaned_page_ids_json))
            if page_ids:
                statement = select(CleanedOcrPageRow.id, CleanedOcrPageRow.review_status).where(
                    CleanedOcrPageRow.source_file_id == source_file_id,
                    CleanedOcrPageRow.id.in_(page_ids),
                )
                page_rows = {row.id: ReviewStatus(row.review_status) for row in (await session.execute(statement)).all()}
            else:
                page_rows = {}
        page_statuses = tuple(page_rows.get(page_id, ReviewStatus.PENDING) for page_id in page_ids)
        return evaluate_publication_gate(
            chunk_status=ReviewStatus(chunk.review_status),
            page_statuses=page_statuses,
        )

    async def chunk_set_publication_gate(self, *, source_file_id: str, chunk_set_id: str) -> PublicationGateDecision:
        statement = (
            select(TextChunkRow.id)
            .where(
                TextChunkRow.source_file_id == source_file_id,
                TextChunkRow.chunk_set_id == chunk_set_id,
            )
            .order_by(TextChunkRow.chunk_index.asc())
        )
        async with self._session_factory() as session:
            chunk_ids = list((await session.execute(statement)).scalars().all())
        if not chunk_ids:
            return PublicationGateDecision(allowed=False, reasons=("chunk_set_empty",))
        reasons = []
        for chunk_id in chunk_ids:
            decision = await self.publication_gate(source_file_id=source_file_id, chunk_id=chunk_id)
            reasons.extend(f"{chunk_id}:{reason}" for reason in decision.reasons)
        return PublicationGateDecision(allowed=not reasons, reasons=tuple(reasons))

    async def get_queue(self, *, source_file_id: str, chunk_set_id: str) -> ReviewQueue:
        async with self._session_factory() as session:
            chunk_set = await session.get(ChunkSetRow, chunk_set_id)
            if chunk_set is None or chunk_set.source_file_id != source_file_id:
                raise ReviewTargetNotFound(f"chunk set {chunk_set_id!r} was not found in the source file")
            chunk_statement = (
                select(TextChunkRow)
                .where(
                    TextChunkRow.source_file_id == source_file_id,
                    TextChunkRow.chunk_set_id == chunk_set_id,
                )
                .order_by(TextChunkRow.chunk_index.asc())
            )
            chunk_rows = list((await session.execute(chunk_statement)).scalars().all())
            page_ids = tuple(dict.fromkeys(page_id for chunk in chunk_rows for page_id in json.loads(chunk.cleaned_page_ids_json)))
            if page_ids:
                page_statement = (
                    select(CleanedOcrPageRow, OcrPageAttemptRow)
                    .join(OcrPageAttemptRow, CleanedOcrPageRow.ocr_attempt_id == OcrPageAttemptRow.id)
                    .where(
                        CleanedOcrPageRow.source_file_id == source_file_id,
                        CleanedOcrPageRow.id.in_(page_ids),
                    )
                    .order_by(CleanedOcrPageRow.page_number.asc(), CleanedOcrPageRow.id.asc())
                )
                page_rows = list((await session.execute(page_statement)).all())
                change_statement = select(TextCleaningChangeRow.cleaned_page_id, func.count()).where(TextCleaningChangeRow.cleaned_page_id.in_(page_ids)).group_by(TextCleaningChangeRow.cleaned_page_id)
                change_counts = {page_id: count for page_id, count in (await session.execute(change_statement)).all()}
            else:
                page_rows = []
                change_counts = {}
        return ReviewQueue(
            document_id=chunk_set.document_id,
            source_file_id=source_file_id,
            chunk_set_id=chunk_set.id,
            split_version=chunk_set.split_version,
            pages=tuple(
                ReviewPageTarget(
                    id=page.id,
                    page_number=page.page_number,
                    folio_label=attempt.folio_label,
                    generation_number=page.generation_number,
                    raw_text=page.raw_text,
                    clean_text=page.clean_text,
                    review_status=ReviewStatus(page.review_status),
                    ocr_confidence=attempt.mean_confidence,
                    rotation_degrees=attempt.rotation_degrees,
                    cleaning_change_count=int(change_counts.get(page.id, 0)),
                )
                for page, attempt in page_rows
            ),
            chunks=tuple(
                ReviewChunkTarget(
                    id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    volume=chunk.volume,
                    item=chunk.item,
                    raw_text=chunk.original_text,
                    clean_text=chunk.normalized_text,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    cleaned_page_ids=tuple(json.loads(chunk.cleaned_page_ids_json)),
                    review_status=ReviewStatus(chunk.review_status),
                )
                for chunk in chunk_rows
            ),
        )

    @staticmethod
    def _record_to_row(record: ReviewRecord) -> ReviewRecordRow:
        return ReviewRecordRow(
            id=record.id,
            document_id=record.document_id,
            source_file_id=record.source_file_id,
            target_type=record.target_type.value,
            target_id=record.target_id,
            revision=record.revision,
            previous_status=record.previous_status.value,
            decision=record.decision.value,
            comment=record.comment,
            batch_id=record.batch_id,
            reviewed_by=record.reviewed_by,
            reviewed_at=record.reviewed_at,
        )

    @staticmethod
    def _row_to_record(row: ReviewRecordRow) -> ReviewRecord:
        return ReviewRecord(
            id=row.id,
            document_id=row.document_id,
            source_file_id=row.source_file_id,
            target_type=ReviewTargetType(row.target_type),
            target_id=row.target_id,
            revision=row.revision,
            previous_status=ReviewStatus(row.previous_status),
            decision=ReviewStatus(row.decision),
            comment=row.comment,
            batch_id=row.batch_id,
            reviewed_by=row.reviewed_by,
            reviewed_at=_with_utc(row.reviewed_at),
        )


class SqlKnowledgeReleaseRepository:
    """Publish immutable manifests and atomically switch one active pointer."""

    _STATE_ID = "active"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        publication_indexer=None,
        publication_assets=None,
    ) -> None:
        self._session_factory = session_factory
        self._publication_indexer = publication_indexer
        self._publication_assets = publication_assets

    async def publish(self, request: PublishReleaseRequest, *, actor_id: str, created_at) -> KnowledgeRelease:
        async with self._session_factory() as session:
            state = await self._state_row(session, lock=True)
            self._check_state_version(state, request.expected_state_version)
            chunk_sets = list((await session.execute(select(ChunkSetRow).where(ChunkSetRow.id.in_(request.chunk_set_ids)))).scalars().all())
            by_id = {row.id: row for row in chunk_sets}
            missing = [chunk_set_id for chunk_set_id in request.chunk_set_ids if chunk_set_id not in by_id]
            if missing:
                raise KnowledgeReleaseNotFound(f"chunk sets not found: {', '.join(missing)}")

            items: list[KnowledgeReleaseItem] = []
            for chunk_set_id in request.chunk_set_ids:
                chunk_set = by_id[chunk_set_id]
                document_row = await session.get(SourceDocumentRow, chunk_set.document_id)
                if document_row is None:
                    raise KnowledgeReleaseNotFound(f"source document {chunk_set.document_id!r} was not found")
                if request.scope == "internal":
                    access = evaluate_source_access(
                        SqlSourceDocumentRepository._row_to_document(document_row),
                        use=AuthorizedUse.INTERNAL_PROCESSING,
                    )
                    if not access.allowed:
                        raise KnowledgeReleaseGateError(f"source document {chunk_set.document_id!r} is not authorized for internal processing: {access.reason}")
                chunks = list((await session.execute(select(TextChunkRow).where(TextChunkRow.chunk_set_id == chunk_set_id).order_by(TextChunkRow.chunk_index.asc()))).scalars().all())
                if not chunks:
                    raise KnowledgeReleaseGateError(f"chunk set {chunk_set_id!r} is empty")
                for chunk in chunks:
                    if request.scope == "public" and chunk.review_status != ReviewStatus.REVIEWED.value:
                        raise KnowledgeReleaseGateError(f"chunk {chunk.id!r} is not reviewed")
                    page_ids = tuple(json.loads(chunk.cleaned_page_ids_json))
                    if not page_ids:
                        raise KnowledgeReleaseGateError(f"chunk {chunk.id!r} has no exact clean page references")
                    if request.scope == "public":
                        pages = list(
                            (
                                await session.execute(
                                    select(CleanedOcrPageRow).where(
                                        CleanedOcrPageRow.source_file_id == chunk.source_file_id,
                                        CleanedOcrPageRow.id.in_(page_ids),
                                    )
                                )
                            )
                            .scalars()
                            .all()
                        )
                        page_statuses = {page.id: page.review_status for page in pages}
                        if any(page_statuses.get(page_id) != ReviewStatus.REVIEWED.value for page_id in page_ids):
                            raise KnowledgeReleaseGateError(f"chunk {chunk.id!r} references a page that is not reviewed")
                    if not chunk.content_sha256:
                        raise KnowledgeReleaseGateError(f"chunk {chunk.id!r} has no content hash")
                    items.append(
                        KnowledgeReleaseItem(
                            ordinal=len(items),
                            document_id=chunk.document_id,
                            source_file_id=chunk.source_file_id,
                            chunk_set_id=chunk_set.id,
                            chunk_id=chunk.id,
                            content_sha256=chunk.content_sha256,
                            cleaned_page_ids=page_ids,
                        )
                    )

            next_version = int((await session.execute(select(func.coalesce(func.max(KnowledgeReleaseRow.version_number), 0)))).scalar_one()) + 1
            release = build_knowledge_release(
                release_id=f"release-{uuid4().hex}",
                version_number=next_version,
                release_notes=request.release_notes,
                scope=request.scope,
                items=tuple(items),
                created_by=actor_id,
                created_at=created_at,
            )
            session.add(self._release_to_row(release))
            await session.flush()
            session.add_all(self._item_to_row(release.id, item) for item in release.items)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise KnowledgeReleaseConflict("knowledge release changed concurrently or the manifest already exists") from exc
        return await self._prepare_release(
            release.id,
            expected_state_version=request.expected_state_version,
            activate=request.activate,
            action=ReleaseAction.PUBLISH,
            actor_id=actor_id,
            changed_at=created_at,
            reason=request.release_notes,
        )

    async def list_releases(self) -> list[KnowledgeRelease]:
        async with self._session_factory() as session:
            rows = list((await session.execute(select(KnowledgeReleaseRow).order_by(KnowledgeReleaseRow.version_number.asc()))).scalars().all())
            return [await self._row_to_release(session, row) for row in rows]

    async def get(self, release_id: str) -> KnowledgeRelease | None:
        async with self._session_factory() as session:
            row = await session.get(KnowledgeReleaseRow, release_id)
            return None if row is None else await self._row_to_release(session, row)

    async def get_state(self) -> KnowledgeReleaseState:
        async with self._session_factory() as session:
            state = await self._state_row(session)
            active = await session.get(KnowledgeReleaseRow, state.active_release_id) if state.active_release_id else None
            return self._state_to_domain(state, active)

    async def get_active(self) -> KnowledgeRelease | None:
        async with self._session_factory() as session:
            state = await self._state_row(session)
            if state.active_release_id is None:
                return None
            row = await session.get(KnowledgeReleaseRow, state.active_release_id)
            if row is None or row.status != ReleaseStatus.ACTIVE.value:
                return None
            return await self._row_to_release(session, row)

    async def activate(self, request: ActivateReleaseRequest, *, actor_id: str, changed_at) -> KnowledgeReleaseState:
        async with self._session_factory() as session:
            state = await self._state_row(session, lock=True)
            self._check_state_version(state, request.expected_state_version)
            row = await session.get(KnowledgeReleaseRow, request.release_id)
            if row is None:
                raise KnowledgeReleaseNotFound(f"knowledge release {request.release_id!r} was not found")
            if state.active_release_id == row.id:
                return self._state_to_domain(state, row)
            if row.status != ReleaseStatus.READY.value:
                raise KnowledgeReleaseGateError(f"knowledge release {row.id!r} is {row.status}, not ready")
            release = await self._row_to_release(session, row)
            await self._ensure_prepared(session, release)
            await self._switch_state(session, state=state, release=row, action=ReleaseAction.ACTIVATE, actor_id=actor_id, changed_at=changed_at, reason=request.reason)
            await self._commit_switch(session)
            return self._state_to_domain(state, row)

    async def rollback(self, request: RollbackReleaseRequest, *, actor_id: str, changed_at) -> KnowledgeReleaseState:
        async with self._session_factory() as session:
            state = await self._state_row(session, lock=True)
            self._check_state_version(state, request.expected_state_version)
            if state.active_release_id is None:
                raise KnowledgeReleaseConflict("there is no active knowledge release to roll back")
            current = await session.get(KnowledgeReleaseRow, state.active_release_id)
            if current is None:
                raise KnowledgeReleaseConflict("the active knowledge release is missing")
            if request.target_release_id:
                target = await session.get(KnowledgeReleaseRow, request.target_release_id)
            else:
                target = (await session.execute(select(KnowledgeReleaseRow).where(KnowledgeReleaseRow.version_number < current.version_number).order_by(KnowledgeReleaseRow.version_number.desc()).limit(1))).scalar_one_or_none()
            if target is None:
                raise KnowledgeReleaseNotFound("no previous knowledge release is available")
            if target.version_number >= current.version_number:
                raise KnowledgeReleaseConflict("rollback target must be older than the active release")
            if target.status != ReleaseStatus.READY.value:
                raise KnowledgeReleaseGateError(f"rollback target {target.id!r} is {target.status}, not ready")
            release = await self._row_to_release(session, target)
            await self._ensure_prepared(session, release)
            await self._switch_state(session, state=state, release=target, action=ReleaseAction.ROLLBACK, actor_id=actor_id, changed_at=changed_at, reason=request.reason)
            await self._commit_switch(session)
            return self._state_to_domain(state, target)

    async def retry(
        self,
        release_id: str,
        request: RetryReleaseRequest,
        *,
        actor_id: str,
        changed_at,
    ) -> KnowledgeRelease:
        async with self._session_factory() as session:
            row = await session.get(KnowledgeReleaseRow, release_id)
            if row is None:
                raise KnowledgeReleaseNotFound(f"knowledge release {release_id!r} was not found")
            if row.status not in {
                ReleaseStatus.FAILED.value,
                ReleaseStatus.PREPARING.value,
            }:
                raise KnowledgeReleaseGateError(f"knowledge release {release_id!r} is {row.status}, not retryable")
        return await self._prepare_release(
            release_id,
            expected_state_version=request.expected_state_version,
            activate=request.activate,
            action=ReleaseAction.PUBLISH,
            actor_id=actor_id,
            changed_at=changed_at,
            reason=f"重试准备知识版本 {release_id}",
        )

    async def _prepare_release(
        self,
        release_id: str,
        *,
        expected_state_version: int,
        activate: bool,
        action: ReleaseAction,
        actor_id: str,
        changed_at,
        reason: str,
    ) -> KnowledgeRelease:
        try:
            async with self._session_factory() as session:
                state = await self._state_row(session, lock=True)
                self._check_state_version(state, expected_state_version)
                row = await session.get(KnowledgeReleaseRow, release_id)
                if row is None:
                    raise KnowledgeReleaseNotFound(f"knowledge release {release_id!r} was not found")
                row.status = ReleaseStatus.PREPARING.value
                row.failure_code = None
                row.failure_message = None
                row.preparation_attempts += 1
                await session.flush()
                release = await self._row_to_release(session, row)
                if self._publication_indexer is not None:
                    await self._publication_indexer.index_release(session, release, indexed_at=changed_at)
                if self._publication_assets is not None:
                    await self._publication_assets.prepare_release(
                        session,
                        release,
                        actor_id=actor_id,
                        created_at=changed_at,
                    )
                row.status = ReleaseStatus.READY.value
                row.ready_at = changed_at
                if activate:
                    await self._switch_state(
                        session,
                        state=state,
                        release=row,
                        action=action,
                        actor_id=actor_id,
                        changed_at=changed_at,
                        reason=reason,
                    )
                await session.commit()
                return await self._row_to_release(session, row)
        except KnowledgeReleaseConflict as exc:
            await self._mark_failed(release_id, exc, failed_at=changed_at)
            raise
        except (KnowledgeReleaseNotFound, KnowledgeReleaseGateError):
            raise
        except Exception as exc:
            await self._mark_failed(release_id, exc, failed_at=changed_at)
            raise KnowledgeReleasePreparationError(
                release_id,
                f"knowledge release preparation failed: {exc}",
            ) from exc

    async def _mark_failed(self, release_id: str, error: Exception, *, failed_at) -> None:
        async with self._session_factory() as session:
            row = await session.get(KnowledgeReleaseRow, release_id)
            if row is None:
                return
            row.status = ReleaseStatus.FAILED.value
            row.failure_code = type(error).__name__
            row.failure_message = str(error)[:4000]
            row.preparation_attempts += 1
            row.ready_at = None
            await session.commit()

    async def _ensure_prepared(self, session: AsyncSession, release: KnowledgeRelease) -> None:
        if self._publication_indexer is not None:
            await self._publication_indexer.ensure_release_ready(session, release)
        if self._publication_assets is not None:
            await self._publication_assets.ensure_release_ready(session, release)

    async def list_events(self) -> list[KnowledgeReleaseEvent]:
        async with self._session_factory() as session:
            rows = list((await session.execute(select(KnowledgeReleaseEventRow).order_by(KnowledgeReleaseEventRow.state_version.asc()))).scalars().all())
        return [
            KnowledgeReleaseEvent(
                id=row.id,
                action=ReleaseAction(row.action),
                previous_release_id=row.previous_release_id,
                new_release_id=row.new_release_id,
                state_version=row.state_version,
                reason=row.reason,
                actor_id=row.actor_id,
                created_at=_with_utc(row.created_at),
            )
            for row in rows
        ]

    async def _state_row(self, session: AsyncSession, *, lock: bool = False) -> KnowledgeReleaseStateRow:
        statement = select(KnowledgeReleaseStateRow).where(KnowledgeReleaseStateRow.id == self._STATE_ID)
        if lock:
            statement = statement.with_for_update()
        row = (await session.execute(statement)).scalar_one_or_none()
        if row is None:
            row = KnowledgeReleaseStateRow(id=self._STATE_ID, active_release_id=None, state_version=0)
            session.add(row)
            await session.flush()
        return row

    @staticmethod
    def _check_state_version(state: KnowledgeReleaseStateRow, expected: int) -> None:
        if state.state_version != expected:
            raise KnowledgeReleaseConflict(f"active release changed concurrently: expected state version {expected}, found {state.state_version}")

    @staticmethod
    async def _switch_state(session: AsyncSession, *, state, release, action, actor_id, changed_at, reason) -> None:
        previous = state.active_release_id
        if previous and previous != release.id:
            previous_row = await session.get(KnowledgeReleaseRow, previous)
            if previous_row is not None:
                previous_row.status = ReleaseStatus.READY.value
        release.status = ReleaseStatus.ACTIVE.value
        release.activated_at = changed_at
        state.active_release_id = release.id
        state.state_version += 1
        state.updated_by = actor_id
        state.updated_at = changed_at
        session.add(
            KnowledgeReleaseEventRow(
                id=f"release-event-{uuid4().hex}",
                action=action.value,
                previous_release_id=previous,
                new_release_id=release.id,
                state_version=state.state_version,
                reason=reason,
                actor_id=actor_id,
                created_at=changed_at,
            )
        )

    @staticmethod
    async def _commit_switch(session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise KnowledgeReleaseConflict("active knowledge release changed concurrently") from exc

    @staticmethod
    def _release_to_row(release: KnowledgeRelease) -> KnowledgeReleaseRow:
        return KnowledgeReleaseRow(
            id=release.id,
            version_number=release.version_number,
            release_notes=release.release_notes,
            scope=release.scope,
            status=release.status.value,
            failure_code=release.failure_code,
            failure_message=release.failure_message,
            preparation_attempts=release.preparation_attempts,
            ready_at=release.ready_at,
            activated_at=release.activated_at,
            manifest_sha256=release.manifest_sha256,
            created_by=release.created_by,
            created_at=release.created_at,
        )

    @staticmethod
    def _item_to_row(release_id: str, item: KnowledgeReleaseItem) -> KnowledgeReleaseItemRow:
        return KnowledgeReleaseItemRow(
            release_id=release_id,
            ordinal=item.ordinal,
            document_id=item.document_id,
            source_file_id=item.source_file_id,
            chunk_set_id=item.chunk_set_id,
            chunk_id=item.chunk_id,
            content_sha256=item.content_sha256,
            cleaned_page_ids_json=json.dumps(item.cleaned_page_ids, ensure_ascii=False),
        )

    @staticmethod
    async def _row_to_release(session: AsyncSession, row: KnowledgeReleaseRow) -> KnowledgeRelease:
        item_rows = list((await session.execute(select(KnowledgeReleaseItemRow).where(KnowledgeReleaseItemRow.release_id == row.id).order_by(KnowledgeReleaseItemRow.ordinal.asc()))).scalars().all())
        return KnowledgeRelease(
            id=row.id,
            version_number=row.version_number,
            version=f"v{row.version_number}",
            release_notes=row.release_notes,
            scope=row.scope,
            status=ReleaseStatus(row.status),
            failure_code=row.failure_code,
            failure_message=row.failure_message,
            preparation_attempts=row.preparation_attempts,
            ready_at=_with_utc(row.ready_at),
            activated_at=_with_utc(row.activated_at),
            manifest_sha256=row.manifest_sha256,
            items=tuple(
                KnowledgeReleaseItem(
                    ordinal=item.ordinal,
                    document_id=item.document_id,
                    source_file_id=item.source_file_id,
                    chunk_set_id=item.chunk_set_id,
                    chunk_id=item.chunk_id,
                    content_sha256=item.content_sha256,
                    cleaned_page_ids=tuple(json.loads(item.cleaned_page_ids_json)),
                )
                for item in item_rows
            ),
            created_by=row.created_by,
            created_at=_with_utc(row.created_at),
        )

    @staticmethod
    def _state_to_domain(state: KnowledgeReleaseStateRow, active: KnowledgeReleaseRow | None) -> KnowledgeReleaseState:
        return KnowledgeReleaseState(
            active_release_id=(state.active_release_id if active is not None and active.status == ReleaseStatus.ACTIVE.value else None),
            active_version=(f"v{active.version_number}" if active is not None and active.status == ReleaseStatus.ACTIVE.value else None),
            state_version=state.state_version,
            updated_by=state.updated_by,
            updated_at=_with_utc(state.updated_at),
        )


class SqlFullTextRepository:
    """Maintain release-scoped database full-text indexes and exact search."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve_release_id(self, release_id: str | None) -> str:
        async with self._session_factory() as session:
            release = await self._resolve_release(session, release_id)
        return release.id

    async def rebuild_release(self, release_id: str, *, indexed_at) -> FullTextIndexResult:
        async with self._session_factory() as session:
            row = await session.get(KnowledgeReleaseRow, release_id)
            if row is None:
                raise FullTextReleaseNotIndexed(f"knowledge release {release_id!r} was not found")
            release = await SqlKnowledgeReleaseRepository._row_to_release(session, row)
            result = await self.index_release(session, release, indexed_at=indexed_at)
            await session.commit()
            return result

    async def index_release(self, session: AsyncSession, release: KnowledgeRelease, *, indexed_at) -> FullTextIndexResult:
        chunk_ids = tuple(item.chunk_id for item in release.items)
        statement = select(TextChunkRow, SourceDocumentRow).join(SourceDocumentRow, TextChunkRow.document_id == SourceDocumentRow.id).where(TextChunkRow.id.in_(chunk_ids))
        pairs = list((await session.execute(statement)).all())
        by_chunk = {chunk.id: (chunk, document) for chunk, document in pairs}
        documents: list[FullTextIndexDocument] = []
        filter_metadata: list[SearchFilterMetadataRow] = []
        for item in release.items:
            pair = by_chunk.get(item.chunk_id)
            if pair is None:
                raise FullTextReleaseNotIndexed(f"release chunk {item.chunk_id!r} was not found")
            chunk, document = pair
            if chunk.document_id != item.document_id or chunk.source_file_id != item.source_file_id or chunk.chunk_set_id != item.chunk_set_id or chunk.content_sha256 != item.content_sha256:
                raise FullTextReleaseNotIndexed(f"release chunk {item.chunk_id!r} no longer matches its immutable manifest")
            documents.append(
                FullTextIndexDocument(
                    id=f"fulltext-{release.id}-{chunk.id}",
                    release_id=release.id,
                    release_version=release.version,
                    document_id=document.id,
                    source_file_id=chunk.source_file_id,
                    chunk_set_id=chunk.chunk_set_id,
                    chunk_id=chunk.id,
                    document_title=document.title,
                    edition=document.edition,
                    source_type=SourceType(document.source_type),
                    source_level=SourceLevel(document.source_level),
                    volume=chunk.volume,
                    item=chunk.item,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    raw_text=chunk.original_text,
                    clean_text=chunk.normalized_text,
                    content_sha256=chunk.content_sha256,
                    indexed_at=indexed_at,
                )
            )
            filter_metadata.append(
                SearchFilterMetadataRow(
                    release_id=release.id,
                    chunk_id=chunk.id,
                    document_id=document.id,
                    edition=document.edition,
                    source_type=document.source_type,
                    source_level=document.source_level,
                    review_status=chunk.review_status,
                    spatial_confidence=None,
                )
            )
        if not documents:
            raise FullTextReleaseNotIndexed("knowledge release has no chunks to index")

        await session.execute(delete(FullTextIndexStateRow).where(FullTextIndexStateRow.release_id == release.id))
        await session.execute(delete(SearchFilterFacetRow).where(SearchFilterFacetRow.release_id == release.id))
        await session.execute(delete(SearchFilterMetadataRow).where(SearchFilterMetadataRow.release_id == release.id))
        await session.execute(delete(FullTextDocumentRow).where(FullTextDocumentRow.release_id == release.id))
        session.add_all(self._document_to_row(document) for document in documents)
        session.add_all(filter_metadata)
        await session.flush()
        evidence_ids = tuple(document.id for document in documents)
        existing_evidence_ids = set((await session.execute(select(EvidenceRow.id).where(EvidenceRow.id.in_(evidence_ids)))).scalars().all())
        session.add_all(
            EvidenceRow(
                id=document.id,
                document_id=document.document_id,
                chunk_id=document.chunk_id,
                quote=document.clean_text,
                source_level=document.source_level.value,
                review_status=by_chunk[document.chunk_id][0].review_status,
            )
            for document in documents
            if document.id not in existing_evidence_ids
        )
        await session.flush()
        if session.bind is not None and session.bind.dialect.name == "sqlite":
            await self._ensure_sqlite_fts(session)
            await session.execute(text("INSERT INTO wu_fulltext_fts(wu_fulltext_fts) VALUES('rebuild')"))
        session.add(
            FullTextIndexStateRow(
                release_id=release.id,
                manifest_sha256=release.manifest_sha256,
                document_count=len(documents),
                status="ready",
                indexed_at=indexed_at,
            )
        )
        await session.flush()
        return FullTextIndexResult(
            release_id=release.id,
            release_version=release.version,
            indexed_chunks=len(documents),
            indexed_at=indexed_at,
        )

    async def ensure_release_ready(self, session: AsyncSession, release: KnowledgeRelease) -> None:
        state = await session.get(FullTextIndexStateRow, release.id)
        if state is None or state.status != "ready" or state.manifest_sha256 != release.manifest_sha256 or state.document_count != len(release.items):
            raise FullTextReleaseNotIndexed(f"knowledge release {release.id!r} does not have a complete full-text index")

    async def search(self, request: FullTextSearchRequest) -> FullTextSearchResponse:
        parsed = parse_fulltext_query(request.query)
        terms = parsed.all_terms
        phrase_groups = tuple(_script_variants(term) for term in parsed.phrases)
        term_groups = tuple(_script_variants(term) for term in parsed.terms)
        search_groups = (*phrase_groups, *term_groups)
        snippet_terms = tuple(dict.fromkeys(variant for variants in search_groups for variant in variants))
        async with self._session_factory() as session:
            release = await self._resolve_release(session, request.release_id)
            await self.ensure_release_ready(session, release)
            statement = (
                select(FullTextDocumentRow)
                .join(
                    SearchFilterMetadataRow,
                    and_(
                        SearchFilterMetadataRow.release_id == FullTextDocumentRow.release_id,
                        SearchFilterMetadataRow.chunk_id == FullTextDocumentRow.chunk_id,
                    ),
                )
                .where(FullTextDocumentRow.release_id == release.id)
            )
            if request.document_ids:
                statement = statement.where(FullTextDocumentRow.document_id.in_(request.document_ids))
            if request.source_types:
                statement = statement.where(FullTextDocumentRow.source_type.in_(tuple(value.value for value in request.source_types)))
            if request.source_levels:
                statement = statement.where(FullTextDocumentRow.source_level.in_(tuple(value.value for value in request.source_levels)))
            statement = _apply_structured_search_filters(statement, request.filters)
            base_statement = statement

            dialect = session.bind.dialect.name if session.bind is not None else ""
            if dialect == "sqlite" and search_groups and all(len(variant) >= 3 for variants in search_groups for variant in variants):
                await self._ensure_sqlite_fts(session)
                match_query = " AND ".join("(" + " OR ".join(f'"{variant.replace(chr(34), chr(34) * 2)}"' for variant in variants) + ")" for variants in search_groups)
                ids = list(
                    (
                        await session.execute(
                            text("SELECT d.id FROM wu_fulltext_fts JOIN wu_fulltext_documents AS d ON d.id = wu_fulltext_fts.rowid WHERE wu_fulltext_fts MATCH :query AND d.release_id = :release_id"),
                            {"query": match_query, "release_id": release.id},
                        )
                    )
                    .scalars()
                    .all()
                )
                if not ids:
                    rows = []
                else:
                    rows = list((await session.execute(statement.where(FullTextDocumentRow.id.in_(ids)))).scalars().all())
            else:
                for variants in search_groups:
                    statement = statement.where(or_(*(FullTextDocumentRow.search_text.contains(variant, autoescape=True) for variant in variants)))
                rows = list((await session.execute(statement)).scalars().all())

            # A natural-language question often contains a subject and an
            # action that are separated differently in the source text. Keep
            # the precise AND result when it exists, then broaden only an
            # empty question to an OR candidate recall. Quoted phrases remain
            # exact and never enter this fallback.
            if not rows and parsed.is_natural_language and not parsed.phrases and len(term_groups) > 1:
                fallback_variants = tuple(
                    dict.fromkeys(variant for variants in term_groups for variant in variants)
                )
                if dialect == "sqlite" and fallback_variants and all(len(variant) >= 3 for variant in fallback_variants):
                    fallback_query = " OR ".join(
                        f'"{variant.replace(chr(34), chr(34) * 2)}"' for variant in fallback_variants
                    )
                    ids = list(
                        (
                            await session.execute(
                                text("SELECT d.id FROM wu_fulltext_fts JOIN wu_fulltext_documents AS d ON d.id = wu_fulltext_fts.rowid WHERE wu_fulltext_fts MATCH :query AND d.release_id = :release_id"),
                                {"query": fallback_query, "release_id": release.id},
                            )
                        )
                        .scalars()
                        .all()
                    )
                    rows = list((await session.execute(base_statement.where(FullTextDocumentRow.id.in_(ids)))).scalars().all()) if ids else []
                elif fallback_variants:
                    rows = list(
                        (
                            await session.execute(
                                base_statement.where(
                                    or_(*(FullTextDocumentRow.search_text.contains(variant, autoescape=True) for variant in fallback_variants))
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )

        async with self._session_factory() as session:
            document_rows = {row.id: row for row in (await session.execute(select(SourceDocumentRow).where(SourceDocumentRow.id.in_(tuple({row.document_id for row in rows}))))).scalars().all()}
            metadata_rows = {
                row.chunk_id: row
                for row in (
                    await session.execute(
                        select(SearchFilterMetadataRow).where(
                            SearchFilterMetadataRow.release_id == release.id,
                            SearchFilterMetadataRow.chunk_id.in_(tuple(row.chunk_id for row in rows)),
                        )
                    )
                )
                .scalars()
                .all()
            }
            chunk_rows = {row.id: row for row in (await session.execute(select(TextChunkRow).where(TextChunkRow.id.in_(tuple(row.chunk_id for row in rows))))).scalars().all()}
            cleaned_page_ids = tuple(dict.fromkeys(page_id for chunk in chunk_rows.values() for page_id in json.loads(chunk.cleaned_page_ids_json)))
            folio_by_cleaned_page_id = {
                cleaned_page_id: folio_label
                for cleaned_page_id, folio_label in (
                    await session.execute(select(CleanedOcrPageRow.id, OcrPageAttemptRow.folio_label).join(OcrPageAttemptRow, CleanedOcrPageRow.ocr_attempt_id == OcrPageAttemptRow.id).where(CleanedOcrPageRow.id.in_(cleaned_page_ids)))
                ).all()
                if folio_label is not None
            }

        hits = []
        for row in rows:
            if is_non_historical_text(row.clean_text):
                continue
            source_row = document_rows.get(row.document_id)
            metadata_row = metadata_rows.get(row.chunk_id)
            chunk_row = chunk_rows.get(row.chunk_id)
            if (
                source_row is None
                or metadata_row is None
                or not evaluate_source_access(
                    SqlSourceDocumentRepository._row_to_document(source_row),
                    use=request.authorized_use,
                ).allowed
            ):
                continue
            folio_labels = tuple(folio_by_cleaned_page_id[page_id] for page_id in json.loads(chunk_row.cleaned_page_ids_json) if page_id in folio_by_cleaned_page_id) if chunk_row is not None else ()
            matched = tuple(term for term, variants in zip(terms, search_groups, strict=True) if any(variant in row.search_text for variant in variants))
            score = _score_script_variant_match(
                title=row.search_title,
                headings=row.search_headings,
                body=row.search_body,
                phrase_groups=phrase_groups,
                term_groups=term_groups,
            )
            hits.append(
                FullTextSearchHit(
                    release_id=release.id,
                    chunk_id=row.chunk_id,
                    score=score,
                    matched_terms=matched,
                    snippet=build_highlighted_snippet(row.clean_text, snippet_terms),
                    citation=Citation(
                        evidence_id=row.external_id,
                        document_id=row.document_id,
                        source_file_id=row.source_file_id,
                        document_title=row.document_title,
                        edition=row.edition,
                        volume=row.volume,
                        section=row.item,
                        page_start=row.page_start,
                        page_end=row.page_end,
                        folio_start=folio_labels[0] if folio_labels else None,
                        folio_end=folio_labels[-1] if folio_labels else None,
                        quote=build_highlighted_snippet(row.clean_text, snippet_terms),
                        source_level=SourceLevel(row.source_level),
                        review_status=ReviewStatus(metadata_row.review_status),
                    ),
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.citation.document_id, hit.chunk_id))
        total = len(hits)
        offset = (request.page - 1) * request.page_size
        return FullTextSearchResponse(
            query=request.query,
            release_id=release.id,
            release_version=release.version,
            total=total,
            page=request.page,
            page_size=request.page_size,
            hits=tuple(hits[offset : offset + request.page_size]),
        )

    @staticmethod
    async def _resolve_release(session: AsyncSession, release_id: str | None) -> KnowledgeRelease:
        if release_id is None:
            state = await session.get(KnowledgeReleaseStateRow, SqlKnowledgeReleaseRepository._STATE_ID)
            release_id = state.active_release_id if state is not None else None
        if release_id is None:
            raise FullTextReleaseNotIndexed("there is no active knowledge release")
        row = await session.get(KnowledgeReleaseRow, release_id)
        if row is None:
            raise FullTextReleaseNotIndexed(f"knowledge release {release_id!r} was not found")
        return await SqlKnowledgeReleaseRepository._row_to_release(session, row)

    @staticmethod
    async def _ensure_sqlite_fts(session: AsyncSession) -> None:
        await session.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS wu_fulltext_fts USING fts5(search_title, search_headings, search_body, content='wu_fulltext_documents', content_rowid='id', tokenize='trigram')"))

    @staticmethod
    def _document_to_row(document: FullTextIndexDocument) -> FullTextDocumentRow:
        search_title = unicodedata.normalize("NFKC", document.document_title).casefold()
        search_headings = unicodedata.normalize("NFKC", document.headings).casefold()
        search_body = unicodedata.normalize("NFKC", f"{document.raw_text}\n{document.clean_text}").casefold()
        return FullTextDocumentRow(
            external_id=document.id,
            release_id=document.release_id,
            release_version=document.release_version,
            document_id=document.document_id,
            source_file_id=document.source_file_id,
            chunk_set_id=document.chunk_set_id,
            chunk_id=document.chunk_id,
            document_title=document.document_title,
            edition=document.edition,
            source_type=document.source_type.value,
            source_level=document.source_level.value,
            volume=document.volume,
            item=document.item,
            page_start=document.page_start,
            page_end=document.page_end,
            raw_text=document.raw_text,
            clean_text=document.clean_text,
            search_title=search_title,
            search_headings=search_headings,
            search_body=search_body,
            search_text="\n".join((search_title, search_headings, search_body)),
            content_sha256=document.content_sha256,
            indexed_at=document.indexed_at,
        )


class SqlVectorRepository:
    """Persist versioned semantic indexes and query them through DB extensions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_build(self, version: VectorIndexVersion, *, expected_state_version: int) -> VectorIndexVersion:
        if version.status is not VectorIndexStatus.BUILDING:
            raise VectorIndexConflict("a new vector index must start in building state")
        async with self._session_factory() as session:
            release = await session.get(KnowledgeReleaseRow, version.release_id)
            if release is None or release.manifest_sha256 != version.release_manifest_sha256:
                raise VectorIndexConflict("vector index release manifest does not match")
            state = await session.get(VectorIndexStateRow, version.release_id)
            actual_version = state.state_version if state is not None else 0
            if actual_version != expected_state_version:
                raise VectorIndexConflict("vector index state changed before the build started")
            if state is None:
                session.add(VectorIndexStateRow(release_id=version.release_id, active_index_id=None, state_version=0, updated_at=None))
            session.add(self._version_to_row(version, base_state_version=expected_state_version))
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise VectorIndexConflict("vector index build already exists or raced with another build") from exc
        return version

    async def complete_build(self, version: VectorIndexVersion, vectors: tuple[tuple[str, tuple[float, ...]], ...]) -> VectorIndexVersion:
        if version.status is not VectorIndexStatus.READY:
            raise VectorIndexConflict("only a ready vector index snapshot can complete a build")
        if len(vectors) != version.item_count or len({chunk_id for chunk_id, _ in vectors}) != len(vectors):
            raise VectorIndexConflict("vector payload does not match the completed item count")
        if any(len(embedding) != version.dimensions for _, embedding in vectors):
            raise ValueError("vector dimension does not match the index")

        async with self._session_factory() as session:
            row = await session.get(VectorIndexVersionRow, version.id)
            if row is None or row.status != VectorIndexStatus.BUILDING.value:
                raise VectorIndexConflict("vector index is missing or no longer building")
            if (
                row.release_id != version.release_id
                or row.release_manifest_sha256 != version.release_manifest_sha256
                or row.embedding_model != version.embedding_model
                or row.embedding_version != version.embedding_version
                or row.dimensions != version.dimensions
            ):
                raise VectorIndexConflict("completed vector index does not match its build snapshot")

            chunk_ids = tuple(chunk_id for chunk_id, _ in vectors)
            documents = list(
                (
                    await session.execute(
                        select(FullTextDocumentRow).where(
                            FullTextDocumentRow.release_id == version.release_id,
                            FullTextDocumentRow.chunk_id.in_(chunk_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_chunk = {document.chunk_id: document for document in documents}
            if set(by_chunk) != set(chunk_ids):
                raise VectorIndexConflict("vector payload contains chunks outside the immutable release index")

            embedding_rows = [
                VectorEmbeddingRow(
                    index_version_id=version.id,
                    release_id=version.release_id,
                    document_id=by_chunk[chunk_id].document_id,
                    source_file_id=by_chunk[chunk_id].source_file_id,
                    chunk_id=chunk_id,
                    dimensions=version.dimensions,
                    embedding=embedding,
                )
                for chunk_id, embedding in vectors
            ]
            session.add_all(embedding_rows)
            await session.flush()
            dialect = session.bind.dialect.name if session.bind is not None else ""
            if dialect == "sqlite":
                await self._ensure_sqlite_vector_table(session, version.dimensions)
                import sqlite_vec

                table_name = self._sqlite_table_name(version.dimensions)
                await session.execute(
                    text(f"INSERT INTO {table_name}(rowid, index_version_id, embedding) VALUES (:rowid, :index_id, :embedding)"),
                    [
                        {
                            "rowid": embedding_row.id,
                            "index_id": version.id,
                            "embedding": sqlite_vec.serialize_float32(embedding),
                        }
                        for embedding_row, (_, embedding) in zip(embedding_rows, vectors, strict=True)
                    ],
                )
            elif dialect == "postgresql":
                await self._ensure_postgres_vector_index(session, version)

            row.status = version.status.value
            row.item_count = version.item_count
            row.error_code = None
            row.error_message = None
            row.completed_at = version.completed_at
            state_result = await session.execute(
                update(VectorIndexStateRow)
                .where(
                    VectorIndexStateRow.release_id == version.release_id,
                    VectorIndexStateRow.state_version == row.base_state_version,
                )
                .values(
                    active_index_id=version.id,
                    state_version=row.base_state_version + 1,
                    updated_at=version.completed_at,
                )
            )
            if state_result.rowcount != 1:
                await session.rollback()
                raise VectorIndexConflict("vector index state changed while the build was running")
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise VectorIndexConflict("vector index completion conflicted with persisted data") from exc
        return version

    async def fail_build(self, version: VectorIndexVersion) -> VectorIndexVersion:
        if version.status is not VectorIndexStatus.FAILED:
            raise VectorIndexConflict("only a failed vector index snapshot can fail a build")
        async with self._session_factory() as session:
            result = await session.execute(
                update(VectorIndexVersionRow)
                .where(VectorIndexVersionRow.id == version.id, VectorIndexVersionRow.status == VectorIndexStatus.BUILDING.value)
                .values(
                    status=version.status.value,
                    error_code=version.error_code,
                    error_message=version.error_message,
                    completed_at=version.completed_at,
                )
            )
            if result.rowcount != 1:
                await session.rollback()
                raise VectorIndexConflict("vector index is missing or no longer building")
            await session.commit()
        return version

    async def get_state(self, release_id: str) -> VectorIndexState:
        async with self._session_factory() as session:
            row = await session.get(VectorIndexStateRow, release_id)
        if row is None:
            return VectorIndexState(release_id=release_id, state_version=0)
        return VectorIndexState(
            release_id=row.release_id,
            active_index_id=row.active_index_id,
            state_version=row.state_version,
            updated_at=_with_utc(row.updated_at),
        )

    async def list_versions(self, release_id: str) -> list[VectorIndexVersion]:
        async with self._session_factory() as session:
            rows = list((await session.execute(select(VectorIndexVersionRow).where(VectorIndexVersionRow.release_id == release_id).order_by(VectorIndexVersionRow.created_at.desc(), VectorIndexVersionRow.id.desc()))).scalars().all())
        return [self._row_to_version(row) for row in rows]

    async def get_active_version(self, release_id: str) -> VectorIndexVersion:
        async with self._session_factory() as session:
            return await self._get_active_version(session, release_id)

    async def resolve_search_version(self, release_id: str | None) -> VectorIndexVersion:
        async with self._session_factory() as session:
            release = await SqlFullTextRepository._resolve_release(session, release_id)
            return await self._get_active_version(session, release.id)

    async def get_release_build_items(self, release_id: str) -> tuple[str, tuple[VectorBuildItem, ...]]:
        async with self._session_factory() as session:
            release_row = await session.get(KnowledgeReleaseRow, release_id)
            if release_row is None:
                raise VectorIndexConflict(f"knowledge release {release_id!r} was not found")
            release = await SqlKnowledgeReleaseRepository._row_to_release(session, release_row)
            await SqlFullTextRepository(self._session_factory).ensure_release_ready(session, release)
            rows = list(
                (
                    await session.execute(
                        select(FullTextDocumentRow, KnowledgeReleaseItemRow.ordinal)
                        .join(
                            KnowledgeReleaseItemRow,
                            and_(
                                KnowledgeReleaseItemRow.release_id == FullTextDocumentRow.release_id,
                                KnowledgeReleaseItemRow.chunk_id == FullTextDocumentRow.chunk_id,
                            ),
                        )
                        .where(FullTextDocumentRow.release_id == release_id)
                        .order_by(KnowledgeReleaseItemRow.ordinal.asc())
                    )
                ).all()
            )
        if len(rows) != len(release.items):
            raise VectorIndexConflict("full-text index does not match the immutable release manifest")
        return release.manifest_sha256, tuple(VectorBuildItem(chunk_id=document.chunk_id, text=document.clean_text) for document, _ordinal in rows)

    async def search_by_vector(self, request: VectorSearchRequest, query_vector: tuple[float, ...]) -> VectorSearchResponse:
        async with self._session_factory() as session:
            release = await SqlFullTextRepository._resolve_release(session, request.release_id)
            version = await self._get_active_version(session, release.id)
            if version.release_manifest_sha256 != release.manifest_sha256:
                raise VectorIndexNotReady("active vector index does not match the immutable release manifest")
            if len(query_vector) != version.dimensions:
                raise ValueError(f"query vector dimension must be {version.dimensions}")

            candidates = await self._nearest_candidates(session, version, query_vector)
            candidate_ids = tuple(row_id for row_id, _ in candidates)
            if not candidate_ids:
                documents = []
            else:
                statement = (
                    select(VectorEmbeddingRow, FullTextDocumentRow, SourceDocumentRow, SearchFilterMetadataRow)
                    .join(
                        FullTextDocumentRow,
                        and_(
                            FullTextDocumentRow.release_id == VectorEmbeddingRow.release_id,
                            FullTextDocumentRow.chunk_id == VectorEmbeddingRow.chunk_id,
                        ),
                    )
                    .join(SourceDocumentRow, SourceDocumentRow.id == VectorEmbeddingRow.document_id)
                    .join(
                        SearchFilterMetadataRow,
                        and_(
                            SearchFilterMetadataRow.release_id == VectorEmbeddingRow.release_id,
                            SearchFilterMetadataRow.chunk_id == VectorEmbeddingRow.chunk_id,
                        ),
                    )
                    .where(VectorEmbeddingRow.id.in_(candidate_ids))
                )
                if request.document_ids:
                    statement = statement.where(VectorEmbeddingRow.document_id.in_(request.document_ids))
                if request.source_types:
                    statement = statement.where(FullTextDocumentRow.source_type.in_(tuple(value.value for value in request.source_types)))
                if request.source_levels:
                    statement = statement.where(FullTextDocumentRow.source_level.in_(tuple(value.value for value in request.source_levels)))
                statement = _apply_structured_search_filters(statement, request.filters)
                documents = list((await session.execute(statement)).all())
            folio_ranges = await _load_chunk_folio_ranges(
                session,
                tuple(document.chunk_id for _, document, _, _ in documents),
            )

        by_id = {embedding.id: (document, source, metadata) for embedding, document, source, metadata in documents}
        hits = []
        for row_id, distance in candidates:
            pair = by_id.get(row_id)
            if pair is None:
                continue
            document, source, metadata = pair
            if is_non_historical_text(document.clean_text):
                continue
            if not evaluate_source_access(SqlSourceDocumentRepository._row_to_document(source), use=request.authorized_use).allowed:
                continue
            similarity = max(-1.0, min(1.0, 1.0 - float(distance)))
            if similarity < request.min_similarity:
                continue
            hits.append(
                VectorSearchHit(
                    release_id=release.id,
                    index_id=version.id,
                    chunk_id=document.chunk_id,
                    similarity=similarity,
                    citation=Citation(
                        evidence_id=f"vector-{version.id}-{document.chunk_id}",
                        document_id=document.document_id,
                        source_file_id=document.source_file_id,
                        document_title=document.document_title,
                        edition=document.edition,
                        volume=document.volume,
                        section=document.item,
                        page_start=document.page_start,
                        page_end=document.page_end,
                        folio_start=folio_ranges.get(document.chunk_id, (None, None))[0],
                        folio_end=folio_ranges.get(document.chunk_id, (None, None))[1],
                        quote=document.clean_text,
                        source_level=SourceLevel(document.source_level),
                        review_status=ReviewStatus(metadata.review_status),
                    ),
                )
            )
            if len(hits) >= request.top_k:
                break
        return VectorSearchResponse(
            query=request.query,
            release_id=release.id,
            index_id=version.id,
            embedding_model=version.embedding_model,
            embedding_version=version.embedding_version,
            hits=tuple(hits),
        )

    async def _nearest_candidates(self, session: AsyncSession, version: VectorIndexVersion, query_vector: tuple[float, ...]) -> list[tuple[int, float]]:
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            import sqlite_vec

            await self._ensure_sqlite_vector_table(session, version.dimensions)
            rows = (
                await session.execute(
                    text(f"SELECT rowid, distance FROM {self._sqlite_table_name(version.dimensions)} WHERE embedding MATCH :query AND k = :k AND index_version_id = :index_id ORDER BY distance"),
                    {
                        "query": sqlite_vec.serialize_float32(query_vector),
                        "k": version.item_count,
                        "index_id": version.id,
                    },
                )
            ).all()
            return [(int(row_id), float(distance)) for row_id, distance in rows]
        if dialect == "postgresql":
            distance = VectorEmbeddingRow.embedding.op("<=>")(list(query_vector)).label("distance")
            rows = (await session.execute(select(VectorEmbeddingRow.id, distance).where(VectorEmbeddingRow.index_version_id == version.id).order_by(distance).limit(version.item_count))).all()
            return [(int(row_id), float(value)) for row_id, value in rows]
        raise VectorIndexNotReady(f"vector search is unsupported for database dialect {dialect!r}")

    @staticmethod
    async def _get_active_version(session: AsyncSession, release_id: str) -> VectorIndexVersion:
        state = await session.get(VectorIndexStateRow, release_id)
        if state is None or state.active_index_id is None:
            raise VectorIndexNotReady(f"knowledge release {release_id!r} has no active vector index")
        row = await session.get(VectorIndexVersionRow, state.active_index_id)
        if row is None or row.release_id != release_id or row.status != VectorIndexStatus.READY.value:
            raise VectorIndexNotReady(f"knowledge release {release_id!r} has no compatible ready vector index")
        return SqlVectorRepository._row_to_version(row)

    @staticmethod
    def _sqlite_table_name(dimensions: int) -> str:
        if not 1 <= dimensions <= 65535:
            raise ValueError("vector dimensions must be between 1 and 65535")
        return f"wu_vector_vec_d{dimensions}"

    @classmethod
    async def _ensure_sqlite_vector_table(cls, session: AsyncSession, dimensions: int) -> None:
        table_name = cls._sqlite_table_name(dimensions)
        await session.execute(text(f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(index_version_id TEXT PARTITION KEY, embedding FLOAT[{dimensions}] DISTANCE_METRIC=cosine)"))

    @staticmethod
    async def _ensure_postgres_vector_index(session: AsyncSession, version: VectorIndexVersion) -> None:
        index_name = f"ix_wu_vector_hnsw_d{version.dimensions}"
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON wu_vector_embeddings USING hnsw ((embedding::vector({version.dimensions})) vector_cosine_ops) WHERE dimensions = {version.dimensions}"))

    @staticmethod
    def _version_to_row(version: VectorIndexVersion, *, base_state_version: int) -> VectorIndexVersionRow:
        return VectorIndexVersionRow(
            id=version.id,
            release_id=version.release_id,
            release_manifest_sha256=version.release_manifest_sha256,
            embedding_model=version.embedding_model,
            embedding_version=version.embedding_version,
            dimensions=version.dimensions,
            status=version.status.value,
            item_count=version.item_count,
            base_state_version=base_state_version,
            error_code=version.error_code,
            error_message=version.error_message,
            created_by=version.created_by,
            created_at=version.created_at,
            completed_at=version.completed_at,
        )

    @staticmethod
    def _row_to_version(row: VectorIndexVersionRow) -> VectorIndexVersion:
        return VectorIndexVersion(
            id=row.id,
            release_id=row.release_id,
            release_manifest_sha256=row.release_manifest_sha256,
            embedding_model=row.embedding_model,
            embedding_version=row.embedding_version,
            dimensions=row.dimensions,
            status=VectorIndexStatus(row.status),
            item_count=row.item_count,
            error_code=row.error_code,
            error_message=row.error_message,
            created_by=row.created_by,
            created_at=_with_utc(row.created_at),
            completed_at=_with_utc(row.completed_at),
        )


class SqlIngestionJobRepository:
    """Persist ingestion snapshots, ordered steps and append-only events."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, job: IngestionJob, event: IngestionEvent) -> tuple[IngestionJob, bool]:
        async with self._session_factory() as session:
            session.add(self._job_to_row(job))
            try:
                # These mappers intentionally have no ORM relationships, so the
                # unit of work cannot infer that the job must precede its rows.
                await session.flush()
                session.add_all(self._step_to_row(job.id, step, sequence) for sequence, step in enumerate(job.steps))
                session.add(self._event_to_row(event))
                await session.commit()
                return job, True
            except IntegrityError:
                await session.rollback()
                existing = await self._get_by_idempotency(session, created_by=job.created_by, idempotency_key=job.idempotency_key)
                if existing is None:
                    raise
                if existing.document_id != job.document_id or existing.source_file_id != job.source_file_id:
                    raise IngestionIdempotencyConflict("idempotency key already belongs to another source file")
                return existing, False

    async def get(self, job_id: str) -> IngestionJob | None:
        async with self._session_factory() as session:
            row = await session.get(IngestionJobRow, job_id)
            if row is None:
                return None
            return await self._row_to_job(session, row)

    async def get_with_context(
        self,
        job_id: str,
    ) -> tuple[IngestionJob, str | None, str | None] | None:
        statement = (
            select(IngestionJobRow, SourceDocumentRow.title, SourceFileRow.original_filename)
            .join(SourceDocumentRow, SourceDocumentRow.id == IngestionJobRow.document_id)
            .join(SourceFileRow, SourceFileRow.id == IngestionJobRow.source_file_id)
            .where(IngestionJobRow.id == job_id)
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).first()
            if row is None:
                return None
            step_rows = (await session.execute(select(IngestionStepRow).where(IngestionStepRow.job_id == job_id).order_by(IngestionStepRow.sequence.asc()))).scalars().all()
        return self._row_to_job_from_steps(row[0], step_rows), row[1], row[2]

    async def list_for_source_file(self, source_file_id: str) -> list[IngestionJob]:
        statement = select(IngestionJobRow).where(IngestionJobRow.source_file_id == source_file_id).order_by(IngestionJobRow.created_at.desc(), IngestionJobRow.id.desc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
            return [await self._row_to_job(session, row) for row in rows]

    async def list_recent(
        self,
        *,
        limit: int = 100,
        statuses: set[IngestionJobStatus] | None = None,
    ) -> list[tuple[IngestionJob, str | None, str | None]]:
        """Return recent jobs with source context in two bounded queries.

        The operations page needs all failed steps at once. Loading each job's
        steps in a separate query would recreate the library page's N+1
        pattern, so the job and step snapshots are fetched in batches.
        """

        if limit < 1:
            raise ValueError("limit must be at least 1")
        statement = (
            select(IngestionJobRow, SourceDocumentRow.title, SourceFileRow.original_filename)
            .join(SourceDocumentRow, SourceDocumentRow.id == IngestionJobRow.document_id)
            .join(SourceFileRow, SourceFileRow.id == IngestionJobRow.source_file_id)
            .order_by(IngestionJobRow.updated_at.desc(), IngestionJobRow.id.desc())
            .limit(limit)
        )
        if statuses:
            statement = statement.where(IngestionJobRow.status.in_(tuple(status.value for status in statuses)))

        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
            if not rows:
                return []
            job_ids = tuple(row[0].id for row in rows)
            step_rows = (await session.execute(select(IngestionStepRow).where(IngestionStepRow.job_id.in_(job_ids)).order_by(IngestionStepRow.job_id.asc(), IngestionStepRow.sequence.asc()))).scalars().all()

        steps_by_job: dict[str, list[IngestionStepRow]] = {}
        for step in step_rows:
            steps_by_job.setdefault(step.job_id, []).append(step)
        return [
            (
                self._row_to_job_from_steps(row[0], steps_by_job.get(row[0].id, ())),
                row[1],
                row[2],
            )
            for row in rows
        ]

    async def list_events(self, job_id: str, *, after_sequence: int = 0) -> list[IngestionEvent]:
        statement = select(IngestionEventRow).where(IngestionEventRow.job_id == job_id, IngestionEventRow.sequence > after_sequence).order_by(IngestionEventRow.sequence.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [self._row_to_event(row) for row in rows]

    async def save(self, job: IngestionJob, event: IngestionEvent, *, expected_version: int) -> None:
        if job.version != expected_version + 1:
            raise ValueError("persisted ingestion transition must increment version exactly once")
        if event.sequence != job.event_sequence:
            raise ValueError("ingestion event sequence must match the job snapshot")
        values = self._job_values(job)
        async with self._session_factory() as session:
            result = await session.execute(update(IngestionJobRow).where(IngestionJobRow.id == job.id, IngestionJobRow.version == expected_version).values(**values))
            if result.rowcount != 1:
                await session.rollback()
                raise IngestionConcurrencyError("ingestion job changed before this transition was saved")
            for sequence, step in enumerate(job.steps):
                step_result = await session.execute(update(IngestionStepRow).where(IngestionStepRow.job_id == job.id, IngestionStepRow.name == step.name.value).values(**self._step_values(step, sequence)))
                if step_result.rowcount != 1:
                    await session.rollback()
                    raise IngestionConcurrencyError("ingestion step rows no longer match the job snapshot")
            session.add(self._event_to_row(event))
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise IngestionConcurrencyError("ingestion event sequence was concurrently written") from exc

    async def try_start_step(
        self,
        job_id: str,
        *,
        step_name: IngestionStepName,
        worker_id: str,
        max_concurrent_jobs: int,
        lease_seconds: int,
        now,
    ) -> IngestionJob | None:
        if max_concurrent_jobs < 1:
            raise ValueError("max_concurrent_jobs must be at least 1")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be at least 1")
        job = await self.get(job_id)
        if job is None:
            return None
        started, event = begin_step(
            job,
            step_name=step_name,
            worker_id=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            now=now,
        )
        running_count = (
            select(func.count())
            .select_from(IngestionJobRow)
            .where(
                IngestionJobRow.status == IngestionJobStatus.RUNNING.value,
                or_(IngestionJobRow.lease_expires_at.is_(None), IngestionJobRow.lease_expires_at >= now),
            )
            .scalar_subquery()
        )
        async with self._session_factory() as session:
            result = await session.execute(
                update(IngestionJobRow)
                .where(
                    IngestionJobRow.id == job.id,
                    IngestionJobRow.version == job.version,
                    running_count < max_concurrent_jobs,
                )
                .values(**self._job_values(started))
            )
            if result.rowcount != 1:
                await session.rollback()
                return None
            for sequence, step in enumerate(started.steps):
                step_result = await session.execute(update(IngestionStepRow).where(IngestionStepRow.job_id == started.id, IngestionStepRow.name == step.name.value).values(**self._step_values(step, sequence)))
                if step_result.rowcount != 1:
                    await session.rollback()
                    raise IngestionConcurrencyError("ingestion step rows no longer match the claimed job")
            session.add(self._event_to_row(event))
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise IngestionConcurrencyError("ingestion step claim raced with another worker") from exc
        return started

    async def renew_lease(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: int,
        now,
    ) -> IngestionJob | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be at least 1")
        new_expiry = now + timedelta(seconds=lease_seconds)
        async with self._session_factory() as session:
            result = await session.execute(
                update(IngestionJobRow)
                .where(
                    IngestionJobRow.id == job_id,
                    IngestionJobRow.status == IngestionJobStatus.RUNNING.value,
                    IngestionJobRow.owner_worker_id == worker_id,
                    or_(IngestionJobRow.lease_expires_at.is_(None), IngestionJobRow.lease_expires_at >= now),
                )
                .values(lease_expires_at=new_expiry, updated_at=now)
            )
            if result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
        return await self.get(job_id)

    async def recover_interrupted(self, *, now, grace_seconds: int = 0) -> list[IngestionJob]:
        if grace_seconds < 0:
            raise ValueError("grace_seconds must be non-negative")
        cutoff = now - timedelta(seconds=grace_seconds)
        statement = (
            select(IngestionJobRow.id)
            .where(
                IngestionJobRow.status == IngestionJobStatus.RUNNING.value,
                or_(IngestionJobRow.lease_expires_at.is_(None), IngestionJobRow.lease_expires_at < cutoff),
            )
            .order_by(IngestionJobRow.created_at.asc())
        )
        async with self._session_factory() as session:
            job_ids = list((await session.execute(statement)).scalars().all())
        recovered: list[IngestionJob] = []
        for job_id in job_ids:
            job = await self.get(job_id)
            if job is None or job.status is not IngestionJobStatus.RUNNING:
                continue
            updated, event = recover_interrupted_job(job, now=now)
            try:
                await self.save(updated, event, expected_version=job.version)
            except IngestionConcurrencyError:
                continue
            recovered.append(updated)
        return recovered

    async def _get_by_idempotency(self, session: AsyncSession, *, created_by: str, idempotency_key: str) -> IngestionJob | None:
        statement = select(IngestionJobRow).where(IngestionJobRow.created_by == created_by, IngestionJobRow.idempotency_key == idempotency_key)
        row = (await session.execute(statement)).scalar_one_or_none()
        return await self._row_to_job(session, row) if row is not None else None

    @staticmethod
    async def _row_to_job(session: AsyncSession, row: IngestionJobRow) -> IngestionJob:
        statement = select(IngestionStepRow).where(IngestionStepRow.job_id == row.id).order_by(IngestionStepRow.sequence.asc())
        step_rows = (await session.execute(statement)).scalars().all()
        return SqlIngestionJobRepository._row_to_job_from_steps(row, step_rows)

    @staticmethod
    def _row_to_job_from_steps(row: IngestionJobRow, step_rows: Sequence[IngestionStepRow]) -> IngestionJob:
        return IngestionJob(
            id=row.id,
            document_id=row.document_id,
            source_file_id=row.source_file_id,
            idempotency_key=row.idempotency_key,
            created_by=row.created_by,
            status=IngestionJobStatus(row.status),
            current_step=IngestionStepName(row.current_step) if row.current_step else None,
            progress_percent=row.progress_percent,
            steps=tuple(
                IngestionStep(
                    name=IngestionStepName(step.name),
                    status=IngestionStepStatus(step.status),
                    attempt_count=step.attempt_count,
                    worker_id=step.worker_id,
                    started_at=_with_utc(step.started_at),
                    finished_at=_with_utc(step.finished_at),
                    output_ref=step.output_ref,
                    error_code=step.error_code,
                    error_message=step.error_message,
                    retryable=bool(step.retryable),
                )
                for step in step_rows
            ),
            error_code=row.error_code,
            error_message=row.error_message,
            owner_worker_id=row.owner_worker_id,
            lease_expires_at=_with_utc(row.lease_expires_at),
            version=row.version,
            event_sequence=row.event_sequence,
            created_at=_with_utc(row.created_at),
            updated_at=_with_utc(row.updated_at),
            completed_at=_with_utc(row.completed_at),
        )

    @staticmethod
    def _row_to_event(row: IngestionEventRow) -> IngestionEvent:
        return IngestionEvent(
            job_id=row.job_id,
            sequence=row.sequence,
            event_type=row.event_type,
            job_status=IngestionJobStatus(row.job_status),
            step_name=IngestionStepName(row.step_name) if row.step_name else None,
            step_status=IngestionStepStatus(row.step_status) if row.step_status else None,
            progress_percent=row.progress_percent,
            error_code=row.error_code,
            error_message=row.error_message,
            actor_id=row.actor_id,
            created_at=_with_utc(row.created_at),
        )

    @classmethod
    def _job_to_row(cls, job: IngestionJob) -> IngestionJobRow:
        return IngestionJobRow(id=job.id, **cls._job_values(job))

    @staticmethod
    def _job_values(job: IngestionJob) -> dict:
        return {
            "document_id": job.document_id,
            "source_file_id": job.source_file_id,
            "idempotency_key": job.idempotency_key,
            "created_by": job.created_by,
            "status": job.status.value,
            "current_step": job.current_step.value if job.current_step else None,
            "progress_percent": job.progress_percent,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "owner_worker_id": job.owner_worker_id,
            "lease_expires_at": job.lease_expires_at,
            "version": job.version,
            "event_sequence": job.event_sequence,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "completed_at": job.completed_at,
        }

    @classmethod
    def _step_to_row(cls, job_id: str, step: IngestionStep, sequence: int) -> IngestionStepRow:
        return IngestionStepRow(job_id=job_id, name=step.name.value, **cls._step_values(step, sequence))

    @staticmethod
    def _step_values(step: IngestionStep, sequence: int) -> dict:
        return {
            "sequence": sequence,
            "status": step.status.value,
            "attempt_count": step.attempt_count,
            "worker_id": step.worker_id,
            "started_at": step.started_at,
            "finished_at": step.finished_at,
            "output_ref": step.output_ref,
            "error_code": step.error_code,
            "error_message": step.error_message,
            "retryable": int(step.retryable),
        }

    @staticmethod
    def _event_to_row(event: IngestionEvent) -> IngestionEventRow:
        return IngestionEventRow(
            job_id=event.job_id,
            sequence=event.sequence,
            event_type=event.event_type,
            job_status=event.job_status.value,
            step_name=event.step_name.value if event.step_name else None,
            step_status=event.step_status.value if event.step_status else None,
            progress_percent=event.progress_percent,
            error_code=event.error_code,
            error_message=event.error_message,
            actor_id=event.actor_id,
            created_at=event.created_at,
        )


def _deduplicate_parents[Parent: (SourceDocument, TextChunk)](values: Iterable[Parent], *, kind: str) -> list[Parent]:
    unique: dict[str, Parent] = {}
    for value in values:
        existing = unique.get(value.id)
        if existing is not None and existing != value:
            raise ValueError(f"Conflicting {kind} definitions for id {value.id!r}")
        unique[value.id] = value
    return list(unique.values())


class SqlEvidenceRepository:
    """Persist complete evidence records in short-lived async sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add_record(self, record: EvidenceRecord) -> None:
        await self.add_records([record])

    async def add_records(self, records: Iterable[EvidenceRecord]) -> None:
        batch = tuple(records)
        if not batch:
            return

        documents = _deduplicate_parents((record.document for record in batch), kind="document")
        chunks = _deduplicate_parents((record.chunk for record in batch), kind="chunk")

        async with self._session_factory() as session:
            try:
                session.add_all([self._document_to_row(document) for document in documents])
                await session.flush()
                session.add_all([self._chunk_to_row(chunk) for chunk in chunks])
                await session.flush()
                session.add_all([self._evidence_to_row(record.evidence) for record in batch])
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise

    async def ensure_chunk_evidence(self, *, chunk_set_id: str) -> int:
        """Create one deterministic evidence row for every chunk in a set.

        Evidence is staged as pending until review or an explicitly authorized
        internal working release admits it. Re-running ingestion only fills
        missing rows and never replaces a reviewed decision.
        """
        async with self._session_factory() as session:
            rows = list((await session.execute(select(TextChunkRow, SourceDocumentRow).join(SourceDocumentRow, SourceDocumentRow.id == TextChunkRow.document_id).where(TextChunkRow.chunk_set_id == chunk_set_id))).all())
            if not rows:
                return 0
            chunk_ids = tuple(chunk.id for chunk, _document in rows)
            existing = set(
                (
                    await session.execute(
                        select(EvidenceRow.chunk_id).where(
                            EvidenceRow.chunk_id.in_(chunk_ids),
                            EvidenceRow.document_id.in_(tuple({document.id for _chunk, document in rows})),
                        )
                    )
                )
                .scalars()
                .all()
            )
            pending_ids: set[str] = set()
            for chunk, document in rows:
                if chunk.id in existing:
                    continue
                pending_ids.add(chunk.id)
                session.add(
                    EvidenceRow(
                        id=f"evidence-{chunk.id}",
                        document_id=document.id,
                        chunk_id=chunk.id,
                        quote=chunk.normalized_text,
                        source_level=document.source_level,
                        review_status=chunk.review_status,
                    )
                )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                # A concurrent worker may have inserted the deterministic rows
                # after the initial existence check. Only treat that exact
                # race as success; propagate unrelated constraint failures.
                inserted_after_race = set((await session.execute(select(EvidenceRow.chunk_id).where(EvidenceRow.chunk_id.in_(pending_ids)))).scalars().all())
                if not pending_ids.issubset(inserted_after_race):
                    raise
            return len(chunk_ids)

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        statement = (
            select(EvidenceRow, TextChunkRow, SourceDocumentRow)
            .join(
                TextChunkRow,
                and_(
                    EvidenceRow.chunk_id == TextChunkRow.id,
                    EvidenceRow.document_id == TextChunkRow.document_id,
                ),
            )
            .join(SourceDocumentRow, EvidenceRow.document_id == SourceDocumentRow.id)
            .where(EvidenceRow.id == evidence_id)
            .limit(1)
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).first()
        if row is None:
            return None
        evidence, chunk, document = row
        return self._rows_to_record(evidence, chunk, document)

    async def list_evidence(self) -> Sequence[EvidenceRecord]:

        statement = (
            select(EvidenceRow, TextChunkRow, SourceDocumentRow)
            .join(
                TextChunkRow,
                and_(
                    EvidenceRow.chunk_id == TextChunkRow.id,
                    EvidenceRow.document_id == TextChunkRow.document_id,
                ),
            )
            .join(SourceDocumentRow, EvidenceRow.document_id == SourceDocumentRow.id)
            .order_by(EvidenceRow.id.asc())
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [self._rows_to_record(evidence, chunk, document) for evidence, chunk, document in rows]

    @staticmethod
    def _document_to_row(document: SourceDocument) -> SourceDocumentRow:
        return SqlSourceDocumentRepository._document_to_row(document)

    @staticmethod
    def _chunk_to_row(chunk: TextChunk) -> TextChunkRow:
        return TextChunkRow(
            id=chunk.id,
            document_id=chunk.document_id,
            volume=chunk.volume,
            section=chunk.section,
            paragraph=chunk.paragraph,
            original_text=chunk.original_text,
            normalized_text=chunk.normalized_text,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            review_status=chunk.review_status.value,
        )

    @staticmethod
    def _evidence_to_row(evidence: Evidence) -> EvidenceRow:
        return EvidenceRow(
            id=evidence.id,
            document_id=evidence.document_id,
            chunk_id=evidence.chunk_id,
            quote=evidence.quote,
            source_level=evidence.source_level.value,
            review_status=evidence.review_status.value,
        )

    @staticmethod
    def _rows_to_record(evidence: EvidenceRow, chunk: TextChunkRow, document: SourceDocumentRow) -> EvidenceRecord:
        return EvidenceRecord(
            document=SourceDocument(
                id=document.id,
                title=document.title,
                edition=document.edition,
                source_type=SourceType(document.source_type),
                source_type_label=document.source_type_label,
                source_level=SourceLevel(document.source_level),
                copyright_status=CopyrightStatus(document.copyright_status),
                source_institution=document.source_institution,
                holder=document.holder,
                status=SourceDocumentStatus(document.status),
                authorization_status=AuthorizationStatus(document.authorization_status),
                authorization_basis=document.authorization_basis,
                authorization_valid_from=_with_utc(document.authorization_valid_from),
                authorization_valid_until=_with_utc(document.authorization_valid_until),
                visibility_scope=VisibilityScope(document.visibility_scope),
                authorized_uses=tuple(AuthorizedUse(use) for use in json.loads(document.authorized_uses_json)),
                authorization_proof_object_key=document.authorization_proof_object_key,
                file_hash=document.file_hash,
                created_by=document.created_by,
                created_at=_with_utc(document.created_at),
                updated_by=document.updated_by,
                updated_at=_with_utc(document.updated_at),
            ),
            chunk=TextChunk(
                id=chunk.id,
                document_id=chunk.document_id,
                volume=chunk.volume,
                section=chunk.section,
                paragraph=chunk.paragraph,
                original_text=chunk.original_text,
                normalized_text=chunk.normalized_text,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                review_status=ReviewStatus(chunk.review_status),
            ),
            evidence=Evidence(
                id=evidence.id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
                quote=evidence.quote,
                source_level=SourceLevel(evidence.source_level),
                review_status=ReviewStatus(evidence.review_status),
            ),
        )
