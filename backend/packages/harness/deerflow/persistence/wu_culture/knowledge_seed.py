from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from wu_culture.entities import EntityCreate
from wu_culture.events import EventCreate
from wu_culture.geo import GeoFeature
from wu_culture.models import ReviewStatus
from wu_culture.relations import RelationCreate

from deerflow.persistence.wu_culture.model import (
    EvidenceRow,
    KnowledgeReleaseItemRow,
    KnowledgeReleaseStateRow,
    SourceDocumentRow,
    WuEntityEvidenceRow,
    WuEntityRow,
    WuEventEvidenceRow,
    WuEventParticipantRow,
    WuGeoEvidenceRow,
    WuGeoFeatureRow,
    WuHistoricalEventRow,
    WuRelationEvidenceRow,
    WuRelationRow,
)


class FuxianzhiKnowledgeSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^fuxianzhi-knowledge-seed-v1$")
    description: str
    entities: tuple[EntityCreate, ...]
    relations: tuple[RelationCreate, ...]
    events: tuple[EventCreate, ...]
    geo_features: tuple[GeoFeature, ...]

    @model_validator(mode="after")
    def validate_seed_policy(self) -> FuxianzhiKnowledgeSeed:
        records = (*self.entities, *self.relations, *self.events, *self.geo_features)
        if any(record.review_status is not ReviewStatus.PENDING for record in records):
            raise ValueError("seed records must remain pending until human review")
        if any(not record.evidence_ids for record in records):
            raise ValueError("every seed record must bind at least one evidence ID")
        if any(entity.id is None for entity in self.entities):
            raise ValueError("seed entities require deterministic IDs")
        if any(relation.id is None for relation in self.relations):
            raise ValueError("seed relations require deterministic IDs")
        if any(event.id is None for event in self.events):
            raise ValueError("seed events require deterministic IDs")
        entity_ids = {entity.id for entity in self.entities}
        if len(entity_ids) != len(self.entities):
            raise ValueError("seed entity IDs must be unique")
        if len({relation.id for relation in self.relations}) != len(self.relations):
            raise ValueError("seed relation IDs must be unique")
        if len({event.id for event in self.events}) != len(self.events):
            raise ValueError("seed event IDs must be unique")
        if len({feature.entity_id for feature in self.geo_features}) != len(self.geo_features):
            raise ValueError("seed geo entity IDs must be unique")
        for relation in self.relations:
            if relation.subject_id not in entity_ids or relation.object_id not in entity_ids:
                raise ValueError(f"relation {relation.id} references an undeclared entity")
        for event in self.events:
            referenced = set(event.participant_entity_ids)
            if event.place_entity_id:
                referenced.add(event.place_entity_id)
            if not referenced <= entity_ids:
                raise ValueError(f"event {event.id} references an undeclared entity")
        if any(feature.entity_id not in entity_ids for feature in self.geo_features):
            raise ValueError("geo feature references an undeclared entity")
        return self


class KnowledgeSeedReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    release_id: str
    evidence_count: int
    created: dict[str, int]
    updated: dict[str, int]
    preserved: dict[str, int]
    dry_run: bool


def seed_evidence_chunk_id(evidence_id: str) -> str | None:
    """Return the stable Chunk ID embedded in a release-derived evidence ID.

    Seed manifests are intentionally reusable across immutable Releases. The
    Release UUID is part of full-text evidence IDs, while the Chunk ID is the
    stable identity shared by Releases.
    """
    value = evidence_id.strip()
    if "-chunk-" in value:
        suffix = value.rsplit("-chunk-", 1)[1]
        return f"chunk-{suffix}" if suffix and not suffix.startswith("chunk-") else suffix
    if value.startswith("evidence-"):
        suffix = value.removeprefix("evidence-")
        return suffix if suffix.startswith("chunk-") else f"chunk-{suffix}" if suffix else None
    return None


def _rebind_seed_records(records, evidence_by_id: dict[str, str], evidence_by_chunk: dict[str, str]):
    rebound = []
    missing: list[str] = []
    for record in records:
        evidence_ids: list[str] = []
        for evidence_id in record.evidence_ids:
            target_id = evidence_by_id.get(evidence_id)
            if target_id is None:
                chunk_id = seed_evidence_chunk_id(evidence_id)
                target_id = evidence_by_chunk.get(chunk_id) if chunk_id else None
            if target_id is None:
                missing.append(evidence_id)
            else:
                evidence_ids.append(target_id)
        rebound.append(record.model_copy(update={"evidence_ids": tuple(dict.fromkeys(evidence_ids))}))
    return tuple(rebound), tuple(sorted(set(missing)))


def load_knowledge_seed(path: str | Path) -> FuxianzhiKnowledgeSeed:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return FuxianzhiKnowledgeSeed.model_validate(payload)


async def apply_knowledge_seed(
    session_factory: async_sessionmaker[AsyncSession],
    seed: FuxianzhiKnowledgeSeed,
    *,
    release_id: str | None = None,
    dry_run: bool = False,
) -> KnowledgeSeedReport:
    created = {kind: 0 for kind in ("entities", "relations", "events", "geo_features")}
    updated = {kind: 0 for kind in created}
    preserved = {kind: 0 for kind in created}
    now = datetime.now(UTC)

    async with session_factory() as session:
        active_state = await session.get(KnowledgeReleaseStateRow, "active")
        target_release_id = release_id or (active_state.active_release_id if active_state else None)
        if not target_release_id:
            raise ValueError("an active knowledge release is required")

        release_evidence_rows = (
            await session.execute(
                select(EvidenceRow.id, EvidenceRow.chunk_id, EvidenceRow.document_id)
                .join(KnowledgeReleaseItemRow, KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id)
                .where(KnowledgeReleaseItemRow.release_id == target_release_id)
            )
        ).all()
        found_evidence = {row.id: row.chunk_id for row in release_evidence_rows}
        evidence_by_chunk: dict[str, str] = {}
        evidence_by_document: dict[str, list[str]] = {}
        for evidence_id, chunk_id, document_id in sorted(release_evidence_rows):
            if evidence_id.startswith("evidence-") or chunk_id not in evidence_by_chunk:
                evidence_by_chunk[chunk_id] = evidence_id
            evidence_by_document.setdefault(document_id, []).append(evidence_id)
        rebound_entities, missing_entities = _rebind_seed_records(seed.entities, found_evidence, evidence_by_chunk)
        rebound_relations, missing_relations = _rebind_seed_records(seed.relations, found_evidence, evidence_by_chunk)
        rebound_events, missing_events = _rebind_seed_records(seed.events, found_evidence, evidence_by_chunk)
        rebound_geo_features, missing_geo_features = _rebind_seed_records(seed.geo_features, found_evidence, evidence_by_chunk)
        missing = sorted({*missing_entities, *missing_relations, *missing_events, *missing_geo_features})
        if missing:
            raise ValueError(f"unknown evidence IDs: {', '.join(missing)}")
        evidence_ids = {evidence_id for record in (*rebound_entities, *rebound_relations, *rebound_events, *rebound_geo_features) for evidence_id in record.evidence_ids}

        for entity in rebound_entities:
            assert entity.id is not None
            row = await session.get(WuEntityRow, entity.id)
            if row is not None and row.review_status != ReviewStatus.PENDING.value:
                preserved["entities"] += 1
                continue
            if row is None:
                row = WuEntityRow(id=entity.id, created_at=now, updated_at=now)
                session.add(row)
                created["entities"] += 1
            else:
                updated["entities"] += 1
            row.canonical_name = entity.canonical_name
            row.entity_type = entity.entity_type.value
            row.dynasty = entity.dynasty
            row.extant_status = entity.extant_status
            row.summary = entity.summary
            row.review_status = ReviewStatus.PENDING.value
            row.release_id = target_release_id
            row.updated_at = now
            await session.execute(delete(WuEntityEvidenceRow).where(WuEntityEvidenceRow.entity_id == entity.id))
            session.add_all(WuEntityEvidenceRow(entity_id=entity.id, evidence_id=evidence_id) for evidence_id in entity.evidence_ids)
        await session.flush()

        # Make every source document visible in the graph. These are source
        # nodes, not historical claims; their edges only mean that the
        # attached entity was extracted from that document's Evidence.
        documents = (
            await session.execute(
                select(SourceDocumentRow)
                .join(KnowledgeReleaseItemRow, KnowledgeReleaseItemRow.document_id == SourceDocumentRow.id)
                .where(KnowledgeReleaseItemRow.release_id == target_release_id)
                .order_by(SourceDocumentRow.id.asc())
            )
        ).scalars().unique().all()
        document_entity_ids: dict[str, str] = {}
        for document in documents:
            document_entity_id = f"source-document-{hashlib.sha256(document.id.encode()).hexdigest()[:24]}"
            document_entity_ids[document.id] = document_entity_id
            row = await session.get(WuEntityRow, document_entity_id)
            if row is not None and row.review_status != ReviewStatus.PENDING.value:
                preserved["entities"] += 1
                continue
            if row is None:
                row = WuEntityRow(id=document_entity_id, created_at=now, updated_at=now)
                session.add(row)
                created["entities"] += 1
            else:
                updated["entities"] += 1
            row.canonical_name = document.title
            row.entity_type = "work"
            row.dynasty = None
            row.extant_status = None
            row.summary = "文献节点；关系和证据可回查至该文献的文本块。"
            row.review_status = ReviewStatus.PENDING.value
            row.release_id = target_release_id
            row.updated_at = now
            await session.execute(delete(WuEntityEvidenceRow).where(WuEntityEvidenceRow.entity_id == document_entity_id))
            session.add_all(
                WuEntityEvidenceRow(entity_id=document_entity_id, evidence_id=evidence_id)
                for evidence_id in evidence_by_document.get(document.id, ())
            )
        await session.flush()

        for relation in rebound_relations:
            assert relation.id is not None
            row = await session.get(WuRelationRow, relation.id)
            if row is not None and row.review_status != ReviewStatus.PENDING.value:
                preserved["relations"] += 1
                continue
            if row is None:
                row = WuRelationRow(id=relation.id, created_at=now, updated_at=now)
                session.add(row)
                created["relations"] += 1
            else:
                updated["relations"] += 1
            row.subject_id = relation.subject_id
            row.relation_type = relation.relation_type.value
            row.object_id = relation.object_id
            row.start_time = relation.start_time
            row.end_time = relation.end_time
            row.confidence = relation.confidence
            row.is_inferred = relation.is_inferred
            row.review_status = ReviewStatus.PENDING.value
            row.release_id = target_release_id
            row.updated_at = now
            await session.execute(delete(WuRelationEvidenceRow).where(WuRelationEvidenceRow.relation_id == relation.id))
            session.add_all(WuRelationEvidenceRow(relation_id=relation.id, evidence_id=evidence_id) for evidence_id in relation.evidence_ids)

        for entity in rebound_entities:
            document_ids = {
                document_id
                for evidence_id in entity.evidence_ids
                for document_id, evidence_values in evidence_by_document.items()
                if evidence_id in evidence_values
            }
            for document_id in sorted(document_ids):
                document_entity_id = document_entity_ids.get(document_id)
                if document_entity_id is None:
                    continue
                relation_id = f"documented-{hashlib.sha256(f'{entity.id}:{document_entity_id}'.encode()).hexdigest()[:24]}"
                row = await session.get(WuRelationRow, relation_id)
                if row is None:
                    row = WuRelationRow(
                        id=relation_id,
                        subject_id=entity.id,
                        relation_type="documented_in",
                        object_id=document_entity_id,
                        confidence=1.0,
                        is_inferred=False,
                        review_status=ReviewStatus.PENDING.value,
                        release_id=target_release_id,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    created["relations"] += 1
                else:
                    updated["relations"] += 1
                await session.execute(delete(WuRelationEvidenceRow).where(WuRelationEvidenceRow.relation_id == relation_id))
                session.add_all(
                    WuRelationEvidenceRow(relation_id=relation_id, evidence_id=evidence_id)
                    for evidence_id in entity.evidence_ids
                    if evidence_id in evidence_by_document.get(document_id, ())
                )

        for event in rebound_events:
            assert event.id is not None
            row = await session.get(WuHistoricalEventRow, event.id)
            if row is not None and row.review_status != ReviewStatus.PENDING.value:
                preserved["events"] += 1
                continue
            if row is None:
                row = WuHistoricalEventRow(id=event.id, created_at=now, updated_at=now)
                session.add(row)
                created["events"] += 1
            else:
                updated["events"] += 1
            row.title = event.title
            row.event_type = event.event_type
            row.start_time = event.start_time
            row.end_time = event.end_time
            row.time_certainty = event.time_certainty.value
            row.place_entity_id = event.place_entity_id
            row.summary = event.summary
            row.is_inferred = event.is_inferred
            row.review_status = ReviewStatus.PENDING.value
            row.release_id = target_release_id
            row.updated_at = now
            await session.execute(delete(WuEventParticipantRow).where(WuEventParticipantRow.event_id == event.id))
            await session.execute(delete(WuEventEvidenceRow).where(WuEventEvidenceRow.event_id == event.id))
            session.add_all(WuEventParticipantRow(event_id=event.id, entity_id=entity_id) for entity_id in event.participant_entity_ids)
            session.add_all(WuEventEvidenceRow(event_id=event.id, evidence_id=evidence_id) for evidence_id in event.evidence_ids)

        for feature in rebound_geo_features:
            row = await session.get(WuGeoFeatureRow, feature.entity_id)
            if row is not None and row.review_status != ReviewStatus.PENDING.value:
                preserved["geo_features"] += 1
                continue
            if row is None:
                row = WuGeoFeatureRow(entity_id=feature.entity_id, created_at=now, updated_at=now)
                session.add(row)
                created["geo_features"] += 1
            else:
                updated["geo_features"] += 1
            row.name = feature.name
            row.longitude = feature.lon
            row.latitude = feature.lat
            row.confidence = feature.confidence.value
            row.basis = feature.basis
            row.geometry_type = feature.geometry_type.value
            row.uncertainty_radius_m = feature.uncertainty_radius_m
            row.area_coordinates_json = json.dumps(feature.area_coordinates, ensure_ascii=False)
            row.extent_source = feature.extent_source.value if feature.extent_source else None
            row.extent_basis = feature.extent_basis
            row.review_status = ReviewStatus.PENDING.value
            row.release_id = target_release_id
            row.updated_at = now
            await session.execute(delete(WuGeoEvidenceRow).where(WuGeoEvidenceRow.entity_id == feature.entity_id))
            session.add_all(WuGeoEvidenceRow(entity_id=feature.entity_id, evidence_id=evidence_id) for evidence_id in feature.evidence_ids)

        await session.flush()
        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return KnowledgeSeedReport(
        release_id=target_release_id,
        evidence_count=len(evidence_ids),
        created=created,
        updated=updated,
        preserved=preserved,
        dry_run=dry_run,
    )
