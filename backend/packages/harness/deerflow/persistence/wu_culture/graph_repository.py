from __future__ import annotations

import hashlib
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from wu_culture.entities import EntityRecord
from wu_culture.extraction import extract_knowledge, is_non_historical_text
from wu_culture.models import EntityType, ReviewStatus
from wu_culture.relations import RelationCreate, RelationRecord, RelationType

from deerflow.persistence.wu_culture.model import (
    AliasIndexRow,
    EvidenceRow,
    KnowledgeReleaseItemRow,
    SourceDocumentRow,
    TextChunkRow,
    WuEntityEvidenceRow,
    WuEntityRow,
    WuEventEvidenceRow,
    WuEventParticipantRow,
    WuHistoricalEventRow,
    WuRelationEvidenceRow,
    WuRelationRow,
)


@lru_cache(maxsize=2)
def _opencc_converter(config: str):
    from opencc import OpenCC

    return OpenCC(config)


@lru_cache(maxsize=4096)
def _script_variants(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).strip()
    return tuple(
        dict.fromkeys(
            (
                normalized,
                _opencc_converter("s2t").convert(normalized),
                _opencc_converter("t2s").convert(normalized),
            )
        )
    )


def _entity_evidence_expression(entity_id, release_id: str | None):  # noqa: ANN001
    statement = (
        select(1)
        .select_from(WuEntityEvidenceRow)
        .join(EvidenceRow, EvidenceRow.id == WuEntityEvidenceRow.evidence_id)
        .where(WuEntityEvidenceRow.entity_id == entity_id)
    )
    if release_id is not None:
        statement = statement.join(
            KnowledgeReleaseItemRow,
            and_(
                KnowledgeReleaseItemRow.release_id == release_id,
                KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id,
                KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id,
            ),
        )
    return statement.exists()


def _entity_scope_expression(release_id: str | None, entity_id=None):  # noqa: ANN001
    target_id = WuEntityRow.id if entity_id is None else entity_id
    has_evidence = _entity_evidence_expression(target_id, release_id)
    if release_id is None:
        return has_evidence
    if entity_id is None:
        return and_(or_(WuEntityRow.release_id == release_id, WuEntityRow.release_id.is_(None)), has_evidence)
    entity_in_release = (
        select(1)
        .select_from(WuEntityRow)
        .where(
            WuEntityRow.id == entity_id,
            or_(WuEntityRow.release_id == release_id, WuEntityRow.release_id.is_(None)),
        )
        .exists()
    )
    return and_(entity_in_release, has_evidence)


def _relation_evidence_expression(relation_id, release_id: str | None):  # noqa: ANN001
    statement = (
        select(1)
        .select_from(WuRelationEvidenceRow)
        .join(EvidenceRow, EvidenceRow.id == WuRelationEvidenceRow.evidence_id)
        .where(WuRelationEvidenceRow.relation_id == relation_id)
    )
    if release_id is not None:
        statement = statement.join(
            KnowledgeReleaseItemRow,
            and_(
                KnowledgeReleaseItemRow.release_id == release_id,
                KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id,
                KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id,
            ),
        )
    return statement.exists()


def _relation_scope_expression(release_id: str | None):
    has_evidence = _relation_evidence_expression(WuRelationRow.id, release_id)
    if release_id is None:
        return or_(has_evidence, and_(WuRelationRow.is_inferred.is_(True), ~_relation_evidence_expression(WuRelationRow.id, None)))
    return and_(
        or_(WuRelationRow.release_id == release_id, WuRelationRow.release_id.is_(None)),
        or_(has_evidence, and_(WuRelationRow.is_inferred.is_(True), ~_relation_evidence_expression(WuRelationRow.id, None))),
    )


async def _entity_is_in_scope(session, entity_id: str, release_id: str | None) -> bool:  # noqa: ANN001
    """Check an ID lookup against the same evidence scope as name lookup."""
    return bool(
        (
            await session.execute(
                select(_entity_scope_expression(release_id, entity_id))
            )
        ).scalar()
    )


class SqlKnowledgeGraphRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def ingest_chunk(
        self,
        *,
        document_id: str,
        source_file_id: str,
        chunk_id: str,
        text: str,
    ) -> int:
        """Extract and idempotently persist evidence-backed graph facts for one chunk."""
        if is_non_historical_text(text):
            return 0
        extracted = extract_knowledge(text)
        async with self._session_factory() as session:
            evidence_ids = (
                await session.execute(
                    select(EvidenceRow.id).where(
                        EvidenceRow.document_id == document_id,
                        EvidenceRow.chunk_id == chunk_id,
                    ).order_by(EvidenceRow.id.asc())
                )
            ).scalars().all()
            if not evidence_ids:
                raise ValueError(f"chunk {chunk_id!r} has no evidence row")

            entity_ids: dict[str, str] = {}
            now = datetime.now(UTC)
            created = 0

            document = await session.get(SourceDocumentRow, document_id)
            if document is None:
                raise ValueError(f"document {document_id!r} does not exist")
            document_entity_id, was_created = await _ensure_entity(
                session,
                canonical_name=document.title,
                entity_type=EntityType.WORK.value,
                summary="文献节点；关系和证据可回查至该文献的文本块。",
                evidence_ids=evidence_ids,
                now=now,
            )
            created += int(was_created)

            for entity in extracted.entities:
                entity_id, was_created = await _ensure_entity(
                    session,
                    canonical_name=entity.name,
                    entity_type=entity.entity_type.value,
                    summary=entity.reason,
                    evidence_ids=evidence_ids,
                    now=now,
                )
                entity_ids[entity.name] = entity_id
                created += int(was_created)

            await session.flush()
            for relation in extracted.relations:
                subject_id = entity_ids.get(relation.subject_name)
                object_id = entity_ids.get(relation.object_name)
                if subject_id is None or object_id is None or subject_id == object_id:
                    continue
                relation_id, was_created = await _ensure_relation(
                    session,
                    subject_id=subject_id,
                    relation_type=relation.relation_type.value,
                    object_id=object_id,
                    evidence_ids=evidence_ids,
                    now=now,
                )
                created += int(was_created)

            for event in extracted.events:
                event_digest = hashlib.sha256(
                    f"{document_id}\x1f{chunk_id}\x1f{event.title}".encode()
                ).hexdigest()[:24]
                event_id = f"event-extracted-{event_digest}"
                if await session.get(WuHistoricalEventRow, event_id) is None:
                    participant_ids = [
                        entity_ids[name]
                        for name, candidate in extracted_entity_map(extracted, entity_ids)
                        if candidate.entity_type is EntityType.PERSON and name in event.title
                    ]
                    session.add(
                        WuHistoricalEventRow(
                            id=event_id,
                            title=event.title,
                            event_type="text_extraction",
                            start_time=event.start_time,
                            end_time=None,
                            time_certainty=event.time_certainty,
                            place_entity_id=entity_ids.get(event.place_name) if event.place_name else None,
                            summary="由文献文本中的明确纪年句抽取，待人工复核。",
                            is_inferred=False,
                            review_status=ReviewStatus.PENDING.value,
                            release_id=None,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    session.add_all(
                        WuEventParticipantRow(event_id=event_id, entity_id=entity_id)
                        for entity_id in dict.fromkeys(participant_ids)
                    )
                    session.add_all(
                        WuEventEvidenceRow(event_id=event_id, evidence_id=evidence_id)
                        for evidence_id in evidence_ids
                    )
                    created += 1

            for entity_id in entity_ids.values():
                _relation_id, was_created = await _ensure_relation(
                    session,
                    subject_id=entity_id,
                    relation_type=RelationType.DOCUMENTED_IN.value,
                    object_id=document_entity_id,
                    evidence_ids=evidence_ids,
                    now=now,
                )
                created += int(was_created)
            await session.commit()
            return created
    async def resolve_entities(self, query: str, *, release_id: str | None = None, limit: int = 10) -> list[EntityRecord]:
        async with self._session_factory() as session:
            by_id = await session.get(WuEntityRow, query)
            if by_id is not None and await _entity_is_in_scope(session, by_id.id, release_id):
                return await self._entity_records(session, [by_id], release_id=release_id)

            variants = _script_variants(query)
            for variant in variants:
                exact_stmt = select(WuEntityRow).where(func.lower(WuEntityRow.canonical_name) == variant.casefold())
                exact_stmt = exact_stmt.where(_entity_scope_expression(release_id))
                exact = (await session.execute(exact_stmt.order_by(WuEntityRow.entity_type.asc(), WuEntityRow.id.asc()).limit(limit))).scalars().all()
                if exact:
                    return await self._entity_records(session, exact, release_id=release_id)

            alias_stmt = select(AliasIndexRow.entity_id).where(
                AliasIndexRow.normalized_alias.in_(tuple(variant.casefold() for variant in variants)),
                AliasIndexRow.review_status == ReviewStatus.REVIEWED.value,
            )
            if release_id is not None:
                alias_stmt = alias_stmt.where(AliasIndexRow.release_id == release_id)
            alias_entity_ids = (await session.execute(alias_stmt.order_by(AliasIndexRow.entity_id.asc()).limit(limit))).scalars().all()
            if alias_entity_ids:
                aliases = (
                    await session.execute(
                        select(WuEntityRow)
                        .where(WuEntityRow.id.in_(alias_entity_ids), _entity_scope_expression(release_id))
                        .order_by(WuEntityRow.entity_type.asc(), WuEntityRow.id.asc())
                    )
                ).scalars().all()
                if aliases:
                    return await self._entity_records(session, aliases, release_id=release_id)

            # A source can contain mixed script variants such as 靈岩山. Compare
            # the canonical names after conversion as a bounded fallback; SQL
            # cannot apply OpenCC to an indexed column safely.
            script_stmt = select(WuEntityRow).where(_entity_scope_expression(release_id))
            script_rows = (await session.execute(script_stmt.order_by(WuEntityRow.entity_type.asc(), WuEntityRow.id.asc()))).scalars().all()
            query_variants = {variant.casefold() for variant in variants}
            script_matches = [
                row
                for row in script_rows
                if query_variants.intersection(variant.casefold() for variant in _script_variants(row.canonical_name))
            ]
            if script_matches:
                return await self._entity_records(session, script_matches[:limit], release_id=release_id)

            fuzzy_stmt = select(WuEntityRow).where(
                or_(*(WuEntityRow.canonical_name.icontains(variant, autoescape=True) for variant in variants)),
                _entity_scope_expression(release_id),
            )
            rows = (await session.execute(fuzzy_stmt.order_by(WuEntityRow.canonical_name.asc(), WuEntityRow.entity_type.asc(), WuEntityRow.id.asc()).limit(limit))).scalars().all()
            return await self._entity_records(session, rows, release_id=release_id)

    async def get_entities(self, entity_ids: Sequence[str], *, release_id: str | None = None) -> list[EntityRecord]:
        if not entity_ids:
            return []
        async with self._session_factory() as session:
            stmt = select(WuEntityRow).where(WuEntityRow.id.in_(set(entity_ids)), _entity_scope_expression(release_id))
            rows = (await session.execute(stmt.order_by(WuEntityRow.id.asc()))).scalars().all()
            return await self._entity_records(session, rows, release_id=release_id)

    async def relations_for_entities(
        self,
        entity_ids: Sequence[str],
        *,
        release_id: str | None = None,
        relation_types: Sequence[str] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RelationRecord]:
        if not entity_ids:
            return []
        async with self._session_factory() as session:
            ids = set(entity_ids)
            stmt = select(WuRelationRow).where(
                or_(WuRelationRow.subject_id.in_(ids), WuRelationRow.object_id.in_(ids)),
                WuRelationRow.review_status != ReviewStatus.REJECTED.value,
                _relation_scope_expression(release_id),
                _entity_scope_expression(release_id, WuRelationRow.subject_id),
                _entity_scope_expression(release_id, WuRelationRow.object_id),
            )
            if relation_types:
                stmt = stmt.where(WuRelationRow.relation_type.in_(set(relation_types)))
            else:
                # The document edge is provenance metadata, not a historical
                # relationship. Keep it queryable explicitly, but do not let
                # it crowd the bounded subject neighborhood by default.
                stmt = stmt.where(
                    WuRelationRow.relation_type != RelationType.DOCUMENTED_IN.value
                )
            rows = (
                await session.execute(
                    stmt.order_by(
                        case(
                            (WuRelationRow.relation_type == RelationType.DOCUMENTED_IN.value, 1),
                            else_=0,
                        ).asc(),
                        WuRelationRow.is_inferred.asc(),
                        WuRelationRow.id.asc(),
                    ).offset(offset).limit(limit)
                )
            ).scalars().all()
            if not rows:
                return []
            evidence_statement = (
                select(WuRelationEvidenceRow.relation_id, WuRelationEvidenceRow.evidence_id)
                .join(EvidenceRow, EvidenceRow.id == WuRelationEvidenceRow.evidence_id)
                .where(WuRelationEvidenceRow.relation_id.in_([row.id for row in rows]))
            )
            if release_id is not None:
                evidence_statement = evidence_statement.join(
                    KnowledgeReleaseItemRow,
                    and_(
                        KnowledgeReleaseItemRow.release_id == release_id,
                        KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id,
                        KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id,
                    ),
                )
            evidence_rows = (
                await session.execute(
                    evidence_statement.order_by(
                        WuRelationEvidenceRow.relation_id.asc(),
                        WuRelationEvidenceRow.evidence_id.asc(),
                    )
                )
            ).all()
            evidence_by_relation: dict[str, list[str]] = {}
            for relation_id, evidence_id in evidence_rows:
                evidence_by_relation.setdefault(relation_id, []).append(evidence_id)
            return [
                RelationRecord(
                    id=row.id,
                    subject_id=row.subject_id,
                    relation_type=RelationType(row.relation_type),
                    object_id=row.object_id,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    confidence=row.confidence,
                    evidence_ids=tuple(evidence_by_relation.get(row.id, ())),
                    is_inferred=row.is_inferred,
                    review_status=ReviewStatus(row.review_status),
                    release_id=row.release_id,
                )
                for row in rows
            ]

    async def create_relation(self, payload: RelationCreate) -> RelationRecord:
        if not payload.evidence_ids and not payload.is_inferred:
            raise ValueError("relation requires evidence or is_inferred=true")
        if payload.subject_id == payload.object_id:
            raise ValueError("subject and object must differ")
        relation_id = payload.id or f"rel-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            if await session.get(WuRelationRow, relation_id) is not None:
                raise ValueError(f"relation already exists: {relation_id}")
            for entity_id in (payload.subject_id, payload.object_id):
                if await session.get(WuEntityRow, entity_id) is None:
                    raise ValueError(f"unknown entity_id: {entity_id}")
            for evidence_id in payload.evidence_ids:
                if await session.get(EvidenceRow, evidence_id) is None:
                    raise ValueError(f"unknown evidence_id: {evidence_id}")
            session.add(
                WuRelationRow(
                    id=relation_id,
                    subject_id=payload.subject_id,
                    relation_type=payload.relation_type.value,
                    object_id=payload.object_id,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                    confidence=payload.confidence,
                    is_inferred=payload.is_inferred,
                    review_status=payload.review_status.value,
                    release_id=payload.release_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add_all(WuRelationEvidenceRow(relation_id=relation_id, evidence_id=evidence_id) for evidence_id in payload.evidence_ids)
            await session.commit()
        rows = await self._relations_by_ids((relation_id,))
        return rows[0]

    async def list_relations(
        self,
        *,
        entity_id: str | None = None,
        relation_types: Sequence[str] | None = None,
        release_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RelationRecord]:
        if entity_id:
            return await self.relations_for_entities(
                (entity_id,),
                relation_types=relation_types,
                release_id=release_id,
                limit=limit,
                offset=offset,
            )
        async with self._session_factory() as session:
            stmt = select(WuRelationRow).where(
                WuRelationRow.review_status != ReviewStatus.REJECTED.value,
                _relation_scope_expression(release_id),
                _entity_scope_expression(release_id, WuRelationRow.subject_id),
                _entity_scope_expression(release_id, WuRelationRow.object_id),
            )
            if relation_types:
                stmt = stmt.where(WuRelationRow.relation_type.in_(set(relation_types)))
            else:
                stmt = stmt.where(
                    WuRelationRow.relation_type != RelationType.DOCUMENTED_IN.value
                )
            ids = (
                await session.execute(
                    stmt.order_by(
                        case(
                            (WuRelationRow.relation_type == RelationType.DOCUMENTED_IN.value, 1),
                            else_=0,
                        ).asc(),
                        WuRelationRow.is_inferred.asc(),
                        WuRelationRow.id.asc(),
                    )
                    .offset(offset)
                    .limit(limit)
                    .with_only_columns(WuRelationRow.id)
                )
            ).scalars().all()
        return await self._relations_by_ids(ids)

    async def delete_relation(self, relation_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(delete(WuRelationRow).where(WuRelationRow.id == relation_id))
            await session.commit()
            return bool(result.rowcount)

    async def review_relation(self, relation_id: str, review_status: ReviewStatus) -> RelationRecord:
        async with self._session_factory() as session:
            row = await session.get(WuRelationRow, relation_id)
            if row is None:
                raise KeyError(relation_id)
            evidence_count = (await session.execute(select(func.count()).select_from(WuRelationEvidenceRow).where(WuRelationEvidenceRow.relation_id == relation_id))).scalar_one()
            if review_status is ReviewStatus.REVIEWED and evidence_count == 0:
                raise ValueError("reviewed relations require at least one evidence_id")
            row.review_status = review_status.value
            row.updated_at = datetime.now(UTC)
            await session.commit()
        return (await self._relations_by_ids((relation_id,)))[0]

    async def _relations_by_ids(self, relation_ids: Sequence[str]) -> list[RelationRecord]:
        if not relation_ids:
            return []
        async with self._session_factory() as session:
            rows = (await session.execute(select(WuRelationRow).where(WuRelationRow.id.in_(set(relation_ids))).order_by(WuRelationRow.id))).scalars().all()
            evidence_rows = (
                await session.execute(
                    select(WuRelationEvidenceRow.relation_id, WuRelationEvidenceRow.evidence_id).where(WuRelationEvidenceRow.relation_id.in_(set(relation_ids))).order_by(WuRelationEvidenceRow.relation_id, WuRelationEvidenceRow.evidence_id)
                )
            ).all()
            evidence_by_relation: dict[str, list[str]] = {}
            for relation_id, evidence_id in evidence_rows:
                evidence_by_relation.setdefault(relation_id, []).append(evidence_id)
            return [
                RelationRecord(
                    id=row.id,
                    subject_id=row.subject_id,
                    relation_type=RelationType(row.relation_type),
                    object_id=row.object_id,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    confidence=row.confidence,
                    evidence_ids=tuple(evidence_by_relation.get(row.id, ())),
                    is_inferred=row.is_inferred,
                    review_status=ReviewStatus(row.review_status),
                    release_id=row.release_id,
                )
                for row in rows
            ]

    async def evidence_locators(self, evidence_ids: Sequence[str]) -> list[dict]:
        if not evidence_ids:
            return []
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        EvidenceRow.id,
                        EvidenceRow.document_id,
                        EvidenceRow.chunk_id,
                        EvidenceRow.source_level,
                        EvidenceRow.review_status,
                        SourceDocumentRow.title,
                        SourceDocumentRow.edition,
                        TextChunkRow.volume,
                        TextChunkRow.section,
                        TextChunkRow.page_start,
                        TextChunkRow.page_end,
                    )
                    .join(SourceDocumentRow, SourceDocumentRow.id == EvidenceRow.document_id)
                    .join(TextChunkRow, TextChunkRow.id == EvidenceRow.chunk_id)
                    .where(EvidenceRow.id.in_(set(evidence_ids)))
                    .order_by(EvidenceRow.id.asc())
                )
            ).all()
            return [
                {
                    "evidence_id": row.id,
                    "document_id": row.document_id,
                    "chunk_id": row.chunk_id,
                    "document_title": row.title,
                    "edition": row.edition,
                    "volume": row.volume,
                    "section": row.section,
                    "page_start": row.page_start,
                    "page_end": row.page_end,
                    "source_level": row.source_level,
                    "review_status": row.review_status,
                }
                for row in rows
            ]

    @staticmethod
    async def _entity_records(
        session,  # noqa: ANN001
        rows: Sequence[WuEntityRow],
        *,
        release_id: str | None = None,
    ) -> list[EntityRecord]:
        if not rows:
            return []
        evidence_statement = (
            select(WuEntityEvidenceRow.entity_id, WuEntityEvidenceRow.evidence_id)
            .join(EvidenceRow, EvidenceRow.id == WuEntityEvidenceRow.evidence_id)
            .where(WuEntityEvidenceRow.entity_id.in_([row.id for row in rows]))
        )
        if release_id is not None:
            evidence_statement = evidence_statement.join(
                KnowledgeReleaseItemRow,
                and_(
                    KnowledgeReleaseItemRow.release_id == release_id,
                    KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id,
                    KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id,
                ),
            )
        evidence_rows = (
            await session.execute(
                evidence_statement.order_by(
                    WuEntityEvidenceRow.entity_id.asc(),
                    WuEntityEvidenceRow.evidence_id.asc(),
                )
            )
        ).all()
        evidence_by_entity: dict[str, list[str]] = {}
        for entity_id, evidence_id in evidence_rows:
            evidence_by_entity.setdefault(entity_id, []).append(evidence_id)
        return [
            EntityRecord(
                id=row.id,
                canonical_name=row.canonical_name,
                entity_type=EntityType(row.entity_type),
                dynasty=row.dynasty,
                extant_status=row.extant_status,
                summary=row.summary,
                review_status=ReviewStatus(row.review_status),
                release_id=row.release_id,
                evidence_ids=tuple(evidence_by_entity.get(row.id, ())),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]


def _stable_entity_id(entity_type: str, name: str) -> str:
    digest = hashlib.sha256(f"{entity_type}\x1f{name.casefold()}".encode()).hexdigest()
    return f"entity-{digest[:24]}"


def _stable_relation_id(subject_id: str, relation_type: str, object_id: str) -> str:
    digest = hashlib.sha256(f"{subject_id}\x1f{relation_type}\x1f{object_id}".encode()).hexdigest()
    return f"relation-{digest[:24]}"


async def _ensure_entity(
    session,  # noqa: ANN001
    *,
    canonical_name: str,
    entity_type: str,
    summary: str,
    evidence_ids: Sequence[str],
    now: datetime,
) -> tuple[str, bool]:
    """Reuse a canonical entity before creating a stable extraction identity."""
    row = (
        await session.execute(
            select(WuEntityRow)
            .where(
                WuEntityRow.canonical_name == canonical_name,
                WuEntityRow.entity_type == entity_type,
            )
            .order_by(WuEntityRow.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    was_created = row is None
    if row is None:
        row = WuEntityRow(
            id=_stable_entity_id(entity_type, canonical_name),
            canonical_name=canonical_name,
            entity_type=entity_type,
            summary=summary,
            review_status=ReviewStatus.PENDING.value,
            release_id=None,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
    elif row.review_status == ReviewStatus.PENDING.value and not row.summary:
        row.summary = summary
        row.updated_at = now
    for evidence_id in evidence_ids:
        if await session.get(WuEntityEvidenceRow, {"entity_id": row.id, "evidence_id": evidence_id}) is None:
            session.add(WuEntityEvidenceRow(entity_id=row.id, evidence_id=evidence_id))
    return row.id, was_created


async def _ensure_relation(
    session,  # noqa: ANN001
    *,
    subject_id: str,
    relation_type: str,
    object_id: str,
    evidence_ids: Sequence[str],
    now: datetime,
) -> tuple[str, bool]:
    row = (
        await session.execute(
            select(WuRelationRow)
            .where(
                WuRelationRow.subject_id == subject_id,
                WuRelationRow.relation_type == relation_type,
                WuRelationRow.object_id == object_id,
            )
            .order_by(WuRelationRow.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    was_created = row is None
    if row is None:
        relation_id = _stable_relation_id(subject_id, relation_type, object_id)
        row = WuRelationRow(
            id=relation_id,
            subject_id=subject_id,
            relation_type=relation_type,
            object_id=object_id,
            confidence=0.75,
            is_inferred=False,
            review_status=ReviewStatus.PENDING.value,
            release_id=None,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
    for evidence_id in evidence_ids:
        if await session.get(WuRelationEvidenceRow, {"relation_id": row.id, "evidence_id": evidence_id}) is None:
            session.add(WuRelationEvidenceRow(relation_id=row.id, evidence_id=evidence_id))
    return row.id, was_created


def extracted_entity_map(extracted, entity_ids: dict[str, str]):  # noqa: ANN001
    """Yield extracted names with their persisted records for event linking."""
    return (
        (entity.name, entity)
        for entity in extracted.entities
        if entity.name in entity_ids
    )
