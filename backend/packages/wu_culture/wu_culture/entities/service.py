from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from wu_culture.models import EntityType, ReviewStatus

from .models import EntityCreate, EntityDetail, EntityRecord, EntityUpdate


class EntityInUseError(RuntimeError):
    """Raised when an entity is still referenced by relations/aliases."""


class EntityValidationError(ValueError):
    """Raised when entity fields or evidence associations are invalid."""


class EntityRepository(Protocol):
    async def list(
        self,
        *,
        entity_type: EntityType | None = None,
        review_status: ReviewStatus | None = None,
        q: str | None = None,
        limit: int = 50,
        release_id: str | None = None,
    ) -> list[EntityRecord]: ...

    async def get(self, entity_id: str) -> EntityRecord | None: ...

    async def create(self, record: EntityRecord) -> EntityRecord: ...

    async def update(self, record: EntityRecord) -> EntityRecord: ...

    async def delete(self, entity_id: str) -> None: ...

    async def relation_reference_count(self, entity_id: str) -> int: ...

    async def alias_reference_count(self, entity_id: str) -> int: ...

    async def evidence_payloads(self, evidence_ids: Sequence[str]) -> list[dict]: ...


class InMemoryEntityRepository:
    def __init__(self) -> None:
        self._items: dict[str, EntityRecord] = {}
        self._relation_refs: dict[str, int] = {}
        self._alias_refs: dict[str, int] = {}
        self._evidence: dict[str, dict] = {}

    def set_relation_refs(self, entity_id: str, count: int) -> None:
        self._relation_refs[entity_id] = count

    def set_alias_refs(self, entity_id: str, count: int) -> None:
        self._alias_refs[entity_id] = count

    def put_evidence(self, evidence_id: str, payload: dict) -> None:
        self._evidence[evidence_id] = payload

    async def list(
        self,
        *,
        entity_type: EntityType | None = None,
        review_status: ReviewStatus | None = None,
        q: str | None = None,
        limit: int = 50,
        release_id: str | None = None,
    ) -> list[EntityRecord]:
        rows = list(self._items.values())
        if entity_type is not None:
            rows = [row for row in rows if row.entity_type is entity_type]
        if review_status is not None:
            rows = [row for row in rows if row.review_status is review_status]
        if q:
            needle = q.casefold()
            rows = [row for row in rows if needle in row.canonical_name.casefold() or needle in (row.summary or "").casefold()]
        rows.sort(key=lambda row: (row.canonical_name, row.id))
        return rows[:limit]

    async def get(self, entity_id: str) -> EntityRecord | None:
        return self._items.get(entity_id)

    async def create(self, record: EntityRecord) -> EntityRecord:
        if record.id in self._items:
            raise EntityValidationError(f"entity already exists: {record.id}")
        self._items[record.id] = record
        return record

    async def update(self, record: EntityRecord) -> EntityRecord:
        if record.id not in self._items:
            raise KeyError(record.id)
        self._items[record.id] = record
        return record

    async def delete(self, entity_id: str) -> None:
        self._items.pop(entity_id, None)

    async def relation_reference_count(self, entity_id: str) -> int:
        return self._relation_refs.get(entity_id, 0)

    async def alias_reference_count(self, entity_id: str) -> int:
        return self._alias_refs.get(entity_id, 0)

    async def evidence_payloads(self, evidence_ids: Sequence[str]) -> list[dict]:
        return [self._evidence[eid] for eid in evidence_ids if eid in self._evidence]


class EntityService:
    def __init__(self, repository: EntityRepository) -> None:
        self._repository = repository

    async def list_entities(
        self,
        *,
        entity_type: EntityType | None = None,
        review_status: ReviewStatus | None = None,
        q: str | None = None,
        limit: int = 50,
        release_id: str | None = None,
    ) -> list[EntityRecord]:
        return await self._repository.list(
            entity_type=entity_type,
            review_status=review_status,
            q=q,
            limit=limit,
            release_id=release_id,
        )

    async def get_detail(self, entity_id: str) -> EntityDetail | None:
        record = await self._repository.get(entity_id)
        if record is None:
            return None
        evidence = await self._repository.evidence_payloads(record.evidence_ids)
        return EntityDetail(**record.model_dump(), evidence=tuple(evidence))

    async def create(self, payload: EntityCreate) -> EntityRecord:
        if not payload.evidence_ids and payload.review_status is ReviewStatus.REVIEWED:
            raise EntityValidationError("reviewed entities require at least one evidence_id")
        await self._validate_evidence_ids(payload.evidence_ids)
        entity_id = payload.id or f"entity-{uuid.uuid4().hex[:12]}"
        record = EntityRecord(
            id=entity_id,
            canonical_name=payload.canonical_name,
            entity_type=payload.entity_type,
            dynasty=payload.dynasty,
            extant_status=payload.extant_status,
            summary=payload.summary,
            review_status=payload.review_status,
            release_id=payload.release_id,
            evidence_ids=payload.evidence_ids,
        )
        return await self._repository.create(record)

    async def update(self, entity_id: str, payload: EntityUpdate) -> EntityRecord:
        existing = await self._repository.get(entity_id)
        if existing is None:
            raise KeyError(entity_id)
        data = existing.model_dump()
        patch = payload.model_dump(exclude_unset=True)
        data.update(patch)
        if patch.get("evidence_ids") is not None:
            data["evidence_ids"] = payload.evidence_ids
        record = EntityRecord.model_validate(data)
        if record.review_status is ReviewStatus.REVIEWED and not record.evidence_ids:
            raise EntityValidationError("reviewed entities require at least one evidence_id")
        await self._validate_evidence_ids(record.evidence_ids)
        return await self._repository.update(record)

    async def _validate_evidence_ids(self, evidence_ids: Sequence[str]) -> None:
        if len(evidence_ids) != len(set(evidence_ids)):
            raise EntityValidationError("evidence_ids must be unique")
        if not evidence_ids:
            return
        payloads = await self._repository.evidence_payloads(evidence_ids)
        found = {str(payload.get("evidence_id")) for payload in payloads}
        missing = [evidence_id for evidence_id in evidence_ids if evidence_id not in found]
        if missing:
            raise EntityValidationError(f"unknown evidence_id: {missing[0]}")

    async def delete(self, entity_id: str, *, force: bool = False) -> None:
        existing = await self._repository.get(entity_id)
        if existing is None:
            raise KeyError(entity_id)
        rel = await self._repository.relation_reference_count(entity_id)
        alias = await self._repository.alias_reference_count(entity_id)
        if (rel or alias) and not force:
            raise EntityInUseError(
                f"entity {entity_id} is referenced by relations={rel}, aliases={alias}; pass force to delete"
            )
        await self._repository.delete(entity_id)
