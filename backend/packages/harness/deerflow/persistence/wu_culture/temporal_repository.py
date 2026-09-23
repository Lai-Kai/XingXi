from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from wu_culture.events import EventCreate, EventRecord, TimeCertainty
from wu_culture.geo import GeoFeature, SpatialConfidence, SpatialExtentSource, SpatialGeometryType
from wu_culture.models import ReviewStatus
from wu_culture.review import ReviewConflictError
from wu_culture.review.graph import GraphReviewRecord

from deerflow.persistence.wu_culture.graph_review import append_graph_review, list_graph_reviews
from deerflow.persistence.wu_culture.model import (
    EvidenceRow,
    WuEntityRow,
    WuEventEvidenceRow,
    WuEventParticipantRow,
    WuGeoEvidenceRow,
    WuGeoFeatureRow,
    WuHistoricalEventRow,
)


class SqlEventRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create(self, payload: EventCreate) -> EventRecord:
        if not payload.evidence_ids and not payload.is_inferred:
            raise ValueError("event requires evidence or is_inferred=true")
        if len(payload.evidence_ids) != len(set(payload.evidence_ids)):
            raise ValueError("event evidence IDs must be unique")
        event_id = payload.id or f"event-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            if await session.get(WuHistoricalEventRow, event_id) is not None:
                raise ValueError(f"event already exists: {event_id}")
            entity_ids = set(payload.participant_entity_ids)
            if payload.place_entity_id:
                entity_ids.add(payload.place_entity_id)
            for entity_id in entity_ids:
                if await session.get(WuEntityRow, entity_id) is None:
                    raise ValueError(f"unknown entity_id: {entity_id}")
            for evidence_id in payload.evidence_ids:
                if await session.get(EvidenceRow, evidence_id) is None:
                    raise ValueError(f"unknown evidence_id: {evidence_id}")
            session.add(
                WuHistoricalEventRow(
                    id=event_id,
                    title=payload.title,
                    event_type=payload.event_type,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                    time_certainty=payload.time_certainty.value,
                    place_entity_id=payload.place_entity_id,
                    summary=payload.summary,
                    is_inferred=payload.is_inferred,
                    review_status=payload.review_status.value,
                    release_id=payload.release_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add_all(WuEventParticipantRow(event_id=event_id, entity_id=entity_id) for entity_id in payload.participant_entity_ids)
            session.add_all(WuEventEvidenceRow(event_id=event_id, evidence_id=evidence_id) for evidence_id in payload.evidence_ids)
            await session.commit()
        return await self.get(event_id, include_rejected=True)  # type: ignore[return-value]

    async def get(self, event_id: str, *, include_rejected: bool = False) -> EventRecord | None:
        rows = await self.list(event_ids=(event_id,), limit=1, include_rejected=include_rejected)
        return rows[0] if rows else None

    async def delete(self, event_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(delete(WuHistoricalEventRow).where(WuHistoricalEventRow.id == event_id))
            await session.commit()
            return bool(result.rowcount)

    async def review(self, event_id: str, review_status: ReviewStatus, *, reviewer_id: str, review_note: str | None = None, expected_status: ReviewStatus | None = None) -> EventRecord:
        async with self._session_factory() as session:
            row = await session.get(WuHistoricalEventRow, event_id)
            if row is None:
                raise KeyError(event_id)
            evidence_count = (await session.execute(select(func.count()).select_from(WuEventEvidenceRow).where(WuEventEvidenceRow.event_id == event_id))).scalar_one()
            if review_status is ReviewStatus.REVIEWED and evidence_count == 0:
                raise ValueError("reviewed events require at least one evidence_id")
            await append_graph_review(session, row, object_type="event", new_status=review_status, reviewer_id=reviewer_id, review_note=review_note, expected_status=expected_status)
            try:
                await session.commit()
            except IntegrityError as exc:
                raise ReviewConflictError("审核状态已被其他人修改，请刷新后重试。") from exc
        record = await self.get(event_id, include_rejected=True)
        if record is None:
            raise KeyError(event_id)
        return record

    async def review_history(self, event_id: str) -> list[GraphReviewRecord]:
        return await list_graph_reviews(self._session_factory, "event", event_id)

    async def list(
        self,
        *,
        event_ids: Sequence[str] | None = None,
        place_entity_id: str | None = None,
        participant_entity_id: str | None = None,
        event_type: str | None = None,
        release_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_rejected: bool = False,
    ) -> list[EventRecord]:
        async with self._session_factory() as session:
            stmt = select(WuHistoricalEventRow)
            if not include_rejected:
                stmt = stmt.where(WuHistoricalEventRow.review_status != ReviewStatus.REJECTED.value)
            if event_ids:
                stmt = stmt.where(WuHistoricalEventRow.id.in_(set(event_ids)))
            if place_entity_id:
                stmt = stmt.where(WuHistoricalEventRow.place_entity_id == place_entity_id)
            if event_type:
                stmt = stmt.where(WuHistoricalEventRow.event_type == event_type)
            if release_id:
                stmt = stmt.where(or_(WuHistoricalEventRow.release_id == release_id, WuHistoricalEventRow.release_id.is_(None)))
            if participant_entity_id:
                stmt = stmt.where(WuHistoricalEventRow.id.in_(select(WuEventParticipantRow.event_id).where(WuEventParticipantRow.entity_id == participant_entity_id)))
            rows = (await session.execute(stmt.order_by(WuHistoricalEventRow.start_time.asc().nulls_last(), WuHistoricalEventRow.id.asc()).offset(offset).limit(limit))).scalars().all()
            if not rows:
                return []
            event_ids_found = [row.id for row in rows]
            participants = (
                await session.execute(
                    select(WuEventParticipantRow.event_id, WuEventParticipantRow.entity_id).where(WuEventParticipantRow.event_id.in_(event_ids_found)).order_by(WuEventParticipantRow.event_id, WuEventParticipantRow.entity_id)
                )
            ).all()
            evidence = (
                await session.execute(select(WuEventEvidenceRow.event_id, WuEventEvidenceRow.evidence_id).where(WuEventEvidenceRow.event_id.in_(event_ids_found)).order_by(WuEventEvidenceRow.event_id, WuEventEvidenceRow.evidence_id))
            ).all()
            participants_by_event: dict[str, list[str]] = {}
            evidence_by_event: dict[str, list[str]] = {}
            for event_id, entity_id in participants:
                participants_by_event.setdefault(event_id, []).append(entity_id)
            for event_id, evidence_id in evidence:
                evidence_by_event.setdefault(event_id, []).append(evidence_id)
            return [
                EventRecord(
                    id=row.id,
                    title=row.title,
                    event_type=row.event_type,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    time_certainty=TimeCertainty(row.time_certainty),
                    place_entity_id=row.place_entity_id,
                    participant_entity_ids=tuple(participants_by_event.get(row.id, ())),
                    summary=row.summary,
                    evidence_ids=tuple(evidence_by_event.get(row.id, ())),
                    is_inferred=row.is_inferred,
                    review_status=ReviewStatus(row.review_status),
                    release_id=row.release_id,
                )
                for row in rows
            ]


class SqlGeoRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def upsert(self, feature: GeoFeature) -> GeoFeature:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            if await session.get(WuEntityRow, feature.entity_id) is None:
                raise ValueError(f"unknown entity_id: {feature.entity_id}")
            for evidence_id in feature.evidence_ids:
                if await session.get(EvidenceRow, evidence_id) is None:
                    raise ValueError(f"unknown evidence_id: {evidence_id}")
            row = await session.get(WuGeoFeatureRow, feature.entity_id)
            if row is None:
                row = WuGeoFeatureRow(entity_id=feature.entity_id, created_at=now, updated_at=now)
                session.add(row)
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
            row.review_status = feature.review_status.value
            row.release_id = feature.release_id
            row.updated_at = now
            await session.execute(delete(WuGeoEvidenceRow).where(WuGeoEvidenceRow.entity_id == feature.entity_id))
            session.add_all(WuGeoEvidenceRow(entity_id=feature.entity_id, evidence_id=evidence_id) for evidence_id in feature.evidence_ids)
            await session.commit()
        return feature

    async def delete(self, entity_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(delete(WuGeoFeatureRow).where(WuGeoFeatureRow.entity_id == entity_id))
            await session.commit()
            return bool(result.rowcount)

    async def list(
        self,
        *,
        entity_ids: Sequence[str] | None = None,
        min_confidence: SpatialConfidence | None = None,
        release_id: str | None = None,
        limit: int = 200,
    ) -> list[GeoFeature]:
        async with self._session_factory() as session:
            stmt = select(WuGeoFeatureRow).where(WuGeoFeatureRow.review_status != ReviewStatus.REJECTED.value)
            if entity_ids:
                stmt = stmt.where(WuGeoFeatureRow.entity_id.in_(set(entity_ids)))
            if release_id:
                stmt = stmt.where(or_(WuGeoFeatureRow.release_id == release_id, WuGeoFeatureRow.release_id.is_(None)))
            rows = (await session.execute(stmt.order_by(WuGeoFeatureRow.entity_id.asc()).limit(limit))).scalars().all()
            if min_confidence:
                rank = {"speculative": 1, "approximate": 2, "exact": 3}
                rows = [row for row in rows if rank[row.confidence] >= rank[min_confidence.value]]
            if not rows:
                return []
            evidence = (
                await session.execute(
                    select(WuGeoEvidenceRow.entity_id, WuGeoEvidenceRow.evidence_id).where(WuGeoEvidenceRow.entity_id.in_([row.entity_id for row in rows])).order_by(WuGeoEvidenceRow.entity_id, WuGeoEvidenceRow.evidence_id)
                )
            ).all()
            evidence_by_entity: dict[str, list[str]] = {}
            for entity_id, evidence_id in evidence:
                evidence_by_entity.setdefault(entity_id, []).append(evidence_id)
            return [
                GeoFeature(
                    entity_id=row.entity_id,
                    name=row.name,
                    lon=row.longitude,
                    lat=row.latitude,
                    confidence=SpatialConfidence(row.confidence),
                    basis=row.basis,
                    geometry_type=SpatialGeometryType(row.geometry_type),
                    uncertainty_radius_m=row.uncertainty_radius_m,
                    area_coordinates=tuple(tuple(pair) for pair in json.loads(row.area_coordinates_json)),
                    extent_source=SpatialExtentSource(row.extent_source) if row.extent_source else None,
                    extent_basis=row.extent_basis,
                    evidence_ids=tuple(evidence_by_entity.get(row.entity_id, ())),
                    review_status=ReviewStatus(row.review_status),
                    release_id=row.release_id,
                )
                for row in rows
            ]
