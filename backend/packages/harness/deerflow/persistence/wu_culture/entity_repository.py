from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from wu_culture.entities.models import EntityRecord
from wu_culture.entities.service import EntityValidationError
from wu_culture.models import EntityType, ReviewStatus

from deerflow.persistence.wu_culture.model import (
    AliasIndexRow,
    EvidenceRow,
    KnowledgeReleaseItemRow,
    WuEntityEvidenceRow,
    WuEntityRow,
    WuRelationRow,
)


def _to_record(row: WuEntityRow, evidence_ids: Sequence[str]) -> EntityRecord:
    return EntityRecord(
        id=row.id,
        canonical_name=row.canonical_name,
        entity_type=EntityType(row.entity_type),
        dynasty=row.dynasty,
        extant_status=row.extant_status,
        summary=row.summary,
        review_status=ReviewStatus(row.review_status),
        release_id=row.release_id,
        evidence_ids=tuple(evidence_ids),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlEntityRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def list(
        self,
        *,
        entity_type: EntityType | None = None,
        review_status: ReviewStatus | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
        release_id: str | None = None,
    ) -> list[EntityRecord]:
        async with self._session_factory() as session:
            stmt = select(WuEntityRow)
            if entity_type is not None:
                stmt = stmt.where(WuEntityRow.entity_type == entity_type.value)
            if review_status is not None:
                stmt = stmt.where(WuEntityRow.review_status == review_status.value)
            if q:
                pattern = f"%{q}%"
                stmt = stmt.where(
                    or_(
                        WuEntityRow.canonical_name.ilike(pattern),
                        WuEntityRow.summary.ilike(pattern),
                    )
                )
            if release_id is not None:
                stmt = stmt.where(
                    or_(
                        WuEntityRow.release_id == release_id,
                        WuEntityRow.release_id.is_(None),
                    ),
                    select(WuEntityEvidenceRow.entity_id)
                    .join(EvidenceRow, EvidenceRow.id == WuEntityEvidenceRow.evidence_id)
                    .join(
                        KnowledgeReleaseItemRow,
                        (KnowledgeReleaseItemRow.release_id == release_id)
                        & (KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id)
                        & (KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id),
                    )
                    .where(WuEntityEvidenceRow.entity_id == WuEntityRow.id)
                    .exists(),
                )
            stmt = stmt.order_by(WuEntityRow.canonical_name.asc(), WuEntityRow.id.asc()).offset(offset).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            result: list[EntityRecord] = []
            for row in rows:
                evidence_ids = (
                    await session.execute(
                        select(WuEntityEvidenceRow.evidence_id).where(WuEntityEvidenceRow.entity_id == row.id)
                    )
                ).scalars().all()
                result.append(_to_record(row, evidence_ids))
            return result

    async def get(self, entity_id: str) -> EntityRecord | None:
        async with self._session_factory() as session:
            row = await session.get(WuEntityRow, entity_id)
            if row is None:
                return None
            evidence_ids = (
                await session.execute(
                    select(WuEntityEvidenceRow.evidence_id).where(WuEntityEvidenceRow.entity_id == entity_id)
                )
            ).scalars().all()
            return _to_record(row, evidence_ids)

    async def create(self, record: EntityRecord) -> EntityRecord:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            if await session.get(WuEntityRow, record.id) is not None:
                raise EntityValidationError(f"entity already exists: {record.id}")
            session.add(
                WuEntityRow(
                    id=record.id,
                    canonical_name=record.canonical_name,
                    entity_type=record.entity_type.value,
                    dynasty=record.dynasty,
                    extant_status=record.extant_status,
                    summary=record.summary,
                    review_status=record.review_status.value,
                    release_id=record.release_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            for evidence_id in record.evidence_ids:
                if await session.get(EvidenceRow, evidence_id) is None:
                    raise EntityValidationError(f"unknown evidence_id: {evidence_id}")
                session.add(WuEntityEvidenceRow(entity_id=record.id, evidence_id=evidence_id))
            await session.commit()
        return await self.get(record.id)  # type: ignore[return-value]

    async def update(self, record: EntityRecord) -> EntityRecord:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            row = await session.get(WuEntityRow, record.id)
            if row is None:
                raise KeyError(record.id)
            row.canonical_name = record.canonical_name
            row.entity_type = record.entity_type.value
            row.dynasty = record.dynasty
            row.extant_status = record.extant_status
            row.summary = record.summary
            row.review_status = record.review_status.value
            row.release_id = record.release_id
            row.updated_at = now
            await session.execute(delete(WuEntityEvidenceRow).where(WuEntityEvidenceRow.entity_id == record.id))
            for evidence_id in record.evidence_ids:
                if await session.get(EvidenceRow, evidence_id) is None:
                    raise EntityValidationError(f"unknown evidence_id: {evidence_id}")
                session.add(WuEntityEvidenceRow(entity_id=record.id, evidence_id=evidence_id))
            await session.commit()
        return await self.get(record.id)  # type: ignore[return-value]

    async def delete(self, entity_id: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(WuEntityRow, entity_id)
            if row is None:
                return
            await session.delete(row)
            await session.commit()

    async def relation_reference_count(self, entity_id: str) -> int:
        async with self._session_factory() as session:
            value = await session.scalar(
                select(func.count())
                .select_from(WuRelationRow)
                .where(or_(WuRelationRow.subject_id == entity_id, WuRelationRow.object_id == entity_id))
            )
            return int(value or 0)

    async def alias_reference_count(self, entity_id: str) -> int:
        async with self._session_factory() as session:
            if not hasattr(AliasIndexRow, "entity_id"):
                return 0
            value = await session.scalar(
                select(func.count()).select_from(AliasIndexRow).where(AliasIndexRow.entity_id == entity_id)
            )
            return int(value or 0)

    async def evidence_payloads(self, evidence_ids: Sequence[str]) -> list[dict]:
        if not evidence_ids:
            return []
        async with self._session_factory() as session:
            rows = (
                await session.execute(select(EvidenceRow).where(EvidenceRow.id.in_(list(evidence_ids))))
            ).scalars().all()
            by_id = {row.id: row for row in rows}
            payload = []
            for evidence_id in evidence_ids:
                row = by_id.get(evidence_id)
                if row is None:
                    continue
                payload.append(
                    {
                        "evidence_id": row.id,
                        "document_id": row.document_id,
                        "chunk_id": row.chunk_id,
                        "quote": row.quote,
                        "source_level": row.source_level,
                        "review_status": row.review_status,
                    }
                )
            return payload
