from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Literal, Protocol

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from wu_culture import ReviewStatus
from wu_culture.geo import (
    DEFAULT_EXTENT_BASIS,
    DEFAULT_UNCERTAINTY_RADIUS_METERS,
    SpatialConfidence,
    SpatialExtentSource,
    SpatialGeometryType,
)

from app.gateway.deps import get_current_user_from_request

router = APIRouter(prefix="/api/map", tags=["map"])

Dynasty = Literal["spring_autumn", "jin", "liang", "tang", "song", "ming", "qing", "modern"]
HeritageStatus = Literal["extant", "site", "uncertain"]
AccessStatus = Literal["public_space", "ticket_or_hours", "religious_site", "view_only", "verify_before_visit"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MapEvidenceMediaOut(_Model):
    url: str
    media_type: Literal["image", "document_page", "model"]
    caption: str


class MapEvidenceOut(_Model):
    id: str
    title: str
    publisher: str
    url: str
    kind: Literal["current_map", "historical_reference", "catalog_reference", "corpus_evidence"]
    retrieved_at: str = "2026-07-29"
    note: str
    quote: str | None = None
    media: tuple[MapEvidenceMediaOut, ...] = ()


class MapEntityReferenceOut(_Model):
    id: str
    name: str
    entity_type: str


class MapPointOut(_Model):
    id: str
    entity_id: str
    name: str
    entity_type: str
    lon: float
    lat: float
    confidence: SpatialConfidence
    basis: str
    geometry_type: SpatialGeometryType = SpatialGeometryType.POINT
    uncertainty_radius_m: float | None = None
    area_coordinates: tuple[tuple[float, float], ...] = ()
    extent_source: SpatialExtentSource | None = None
    extent_basis: str | None = None
    coordinate_system: Literal["WGS84"] = "WGS84"
    dynasties: tuple[Dynasty, ...]
    heritage_status: HeritageStatus
    access_status: AccessStatus
    summary: str
    address: str
    evidence: tuple[MapEvidenceOut, ...]
    review_status: ReviewStatus | None = None
    release_id: str | None = None
    record_kind: Literal["reference", "corpus"] = "reference"
    start_year: int | None = None
    end_year: int | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_point(cls, value):  # noqa: ANN001, ANN206
        if not isinstance(value, dict) or "geometry_type" in value:
            return value
        confidence = SpatialConfidence(value.get("confidence", SpatialConfidence.EXACT))
        migrated = dict(value)
        if confidence is SpatialConfidence.EXACT:
            migrated["geometry_type"] = SpatialGeometryType.POINT
        else:
            migrated.update(
                geometry_type=SpatialGeometryType.UNCERTAINTY_RADIUS,
                uncertainty_radius_m=DEFAULT_UNCERTAINTY_RADIUS_METERS[confidence],
                extent_source=SpatialExtentSource.CONFIDENCE_DEFAULT,
                extent_basis=DEFAULT_EXTENT_BASIS,
            )
        return migrated

    @model_validator(mode="after")
    def validate_spatial_representation(self) -> MapPointOut:
        if self.confidence is not SpatialConfidence.EXACT and self.geometry_type is SpatialGeometryType.POINT:
            raise ValueError("non-exact map records must expose an uncertainty area")
        if self.geometry_type is SpatialGeometryType.UNCERTAINTY_RADIUS and self.uncertainty_radius_m is None:
            raise ValueError("uncertainty-radius map records require a radius")
        if self.geometry_type is SpatialGeometryType.HISTORICAL_AREA and len(self.area_coordinates) < 4:
            raise ValueError("historical-area map records require polygon coordinates")
        return self


class MapLayerOut(_Model):
    id: str
    name: str
    kind: Literal["base", "historical"]
    available: bool
    source_url: str
    attribution: str
    calibration_note: str
    tile_url: str | None = None


class TimelineEventOut(_Model):
    id: str
    title: str
    year_start: int | None
    year_end: int | None
    time_label: str
    precision: Literal["exact", "period", "unknown"]
    point_id: str
    summary: str
    evidence: tuple[MapEvidenceOut, ...]
    review_status: ReviewStatus | None = None
    release_id: str | None = None
    record_kind: Literal["reference", "corpus"] = "reference"
    featured: bool = False
    importance: Literal["landmark", "notable", "context"] = "context"
    participants: tuple[MapEntityReferenceOut, ...] = ()


class MapRelationOut(_Model):
    id: str
    subject_id: str
    subject_name: str
    subject_type: str
    relation_type: str
    object_id: str
    object_name: str
    object_type: str
    start_time: str | None = None
    end_time: str | None = None
    confidence: float
    evidence: tuple[MapEvidenceOut, ...]
    review_status: ReviewStatus | None = None
    release_id: str | None = None
    record_kind: Literal["reference", "corpus"] = "reference"


class TrajectoryPointOut(_Model):
    id: str
    point_id: str
    year_start: int | None
    year_end: int | None
    time_label: str
    label: str
    confidence: SpatialConfidence
    evidence: tuple[MapEvidenceOut, ...]
    review_status: ReviewStatus | None = None
    source_record_id: str | None = None


class PersonTrajectoryOut(_Model):
    id: str
    person_id: str
    person_name: str
    summary: str
    has_uncertain_segments: bool
    disclaimer: str
    points: tuple[TrajectoryPointOut, ...]
    review_status: ReviewStatus | None = None
    release_id: str | None = None
    record_kind: Literal["reference", "corpus"] = "reference"


class StudyRouteOut(_Model):
    id: str
    name: str
    duration: Literal["half_day", "full_day"]
    audience: str
    summary: str
    stop_ids: tuple[str, ...]
    disclaimer: str
    evidence: tuple[MapEvidenceOut, ...]


class MapCatalogOut(_Model):
    updated_at: str
    data_notice: str
    points: tuple[MapPointOut, ...]
    layers: tuple[MapLayerOut, ...]
    events: tuple[TimelineEventOut, ...]
    relations: tuple[MapRelationOut, ...] = ()
    trajectories: tuple[PersonTrajectoryOut, ...]
    routes: tuple[StudyRouteOut, ...]


class VersionedCatalogSource(Protocol):
    async def load(self) -> MapCatalogOut | None: ...


class MapCatalogSnapshotUnavailable(RuntimeError):
    """The active release has no valid persisted map snapshot."""


def get_versioned_catalog_source() -> VersionedCatalogSource | None:
    from deerflow.persistence.engine import get_session_factory

    session_factory = get_session_factory()
    return _SqlVersionedCatalogSource(session_factory) if session_factory is not None else None


class _SqlVersionedCatalogSource:
    def __init__(self, session_factory) -> None:  # noqa: ANN001
        self._session_factory = session_factory

    async def load(self) -> MapCatalogOut | None:
        from deerflow.persistence.wu_culture import SqlKnowledgeReleaseRepository

        release = await SqlKnowledgeReleaseRepository(self._session_factory).get_active()
        if release is None:
            return None
        async with self._session_factory() as session:
            try:
                row = (
                    await session.execute(
                        text(
                            "SELECT map_manifest_json,map_manifest_sha256 "
                            "FROM wu_asset_versions "
                            "WHERE knowledge_release_id=:release_id"
                        ),
                        {"release_id": release.id},
                    )
                ).mappings().first()
            except Exception as exc:
                raise MapCatalogSnapshotUnavailable(
                    f"map snapshot schema is unavailable for release {release.id!r}"
                ) from exc
        if row is None or not row["map_manifest_json"]:
            raise MapCatalogSnapshotUnavailable(
                f"active knowledge release {release.id!r} has no persisted map snapshot"
            )
        try:
            payload = json.loads(row["map_manifest_json"])
            actual_hash = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if actual_hash != row["map_manifest_sha256"]:
                raise ValueError("map snapshot hash does not match its persisted body")
            catalog = MapCatalogOut.model_validate(payload)
            # Layer metadata is deployment configuration rather than release
            # content. Keep older snapshots usable after the layer feature is
            # enabled, while still preserving any explicitly published layers.
            return catalog.model_copy(update={"layers": catalog.layers or LAYERS})
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MapCatalogSnapshotUnavailable(
                f"persisted map snapshot for release {release.id!r} is invalid"
            ) from exc

    async def build_live_catalog(self, release) -> MapCatalogOut:  # noqa: ANN001
        from deerflow.persistence.wu_culture import (
            SqlEntityRepository,
            SqlEventRepository,
            SqlEvidenceRepository,
            SqlGeoRepository,
            SqlKnowledgeGraphRepository,
        )

        geo_rows = await SqlGeoRepository(self._session_factory).list(
            release_id=release.id,
            limit=500,
        )
        geo_rows = [row for row in geo_rows if row.release_id == release.id and row.review_status is not ReviewStatus.REJECTED and row.evidence_ids]
        entity_repository = SqlEntityRepository(self._session_factory)
        evidence_repository = SqlEvidenceRepository(self._session_factory)
        entities = {feature.entity_id: await entity_repository.get(feature.entity_id) for feature in geo_rows}
        events = await SqlEventRepository(self._session_factory).list(
            release_id=release.id,
            limit=500,
        )
        events = [event for event in events if event.release_id == release.id and event.review_status is not ReviewStatus.REJECTED and event.evidence_ids]
        relations = await SqlKnowledgeGraphRepository(self._session_factory).list_relations(
            release_id=release.id,
            limit=500,
        )
        relations = [relation for relation in relations if relation.release_id == release.id and relation.review_status is not ReviewStatus.REJECTED and relation.evidence_ids]
        evidence_ids = {
            evidence_id
            for values in (
                *(feature.evidence_ids for feature in geo_rows),
                *(event.evidence_ids for event in events),
                *(relation.evidence_ids for relation in relations),
            )
            for evidence_id in values
        }
        evidence_records = {evidence_id: await evidence_repository.get_evidence(evidence_id) for evidence_id in evidence_ids}

        point_years = _place_time_bounds(events)
        points = tuple(
            self._point(
                feature,
                entities.get(feature.entity_id),
                evidence_records,
                time_bounds=point_years.get(feature.entity_id),
            )
            for feature in geo_rows
            if entities.get(feature.entity_id) is not None and entities[feature.entity_id].release_id == release.id and entities[feature.entity_id].review_status is not ReviewStatus.REJECTED and feature.evidence_ids
        )
        point_ids = {point.entity_id: point.id for point in points}
        graph_entity_ids = {entity_id for relation in relations for entity_id in (relation.subject_id, relation.object_id)} | {entity_id for event in events for entity_id in event.participant_entity_ids}
        for entity in await SqlKnowledgeGraphRepository(self._session_factory).get_entities(
            tuple(graph_entity_ids),
            release_id=release.id,
        ):
            entities[entity.id] = entity
        timeline = tuple(
            self._event(
                event,
                point_ids[event.place_entity_id],
                evidence_records,
                entities,
            )
            for event in events
            if event.place_entity_id in point_ids and event.evidence_ids
        )
        map_relations = _map_relations(tuple(relations), entities, evidence_records)
        trajectories = _derive_person_trajectories(
            points=points,
            entities=entities,
            events=tuple(events),
            relations=tuple(relations),
            evidence_records=evidence_records,
        )
        draft_count = sum(point.review_status is not ReviewStatus.REVIEWED for point in points)
        return MapCatalogOut(
            updated_at=release.created_at.astimezone(UTC).date().isoformat(),
            data_notice=(f"当前地图合并知识版本 {release.version}（{release.scope}）中的证据绑定记录；其中 {draft_count} 个点位为待复核语料草稿。非精确古地点以不确定范围或史料范围显示，中心仅用于检索与交互，不代表历史精确坐标。"),
            points=points,
            layers=LAYERS,
            events=timeline,
            relations=map_relations,
            trajectories=trajectories,
            routes=(),
        )

    @staticmethod
    def _point(feature, entity, evidence_records: dict, *, time_bounds: tuple[int | None, int | None] | None = None) -> MapPointOut:  # noqa: ANN001
        dynasties = _dynasties(entity.dynasty)
        start_year, end_year = time_bounds or (None, None)
        return MapPointOut(
            id=f"corpus-{feature.entity_id}",
            entity_id=feature.entity_id,
            name=feature.name,
            entity_type=entity.entity_type.value,
            lon=feature.lon,
            lat=feature.lat,
            confidence=feature.confidence,
            basis=feature.basis,
            geometry_type=feature.geometry_type,
            uncertainty_radius_m=feature.uncertainty_radius_m,
            area_coordinates=feature.area_coordinates,
            extent_source=feature.extent_source,
            extent_basis=feature.extent_basis,
            dynasties=dynasties,
            heritage_status=_heritage_status(entity.extant_status),
            access_status="verify_before_visit",
            summary=entity.summary or "府县志地点记录，详情待补充。",
            address="历史地点，范围与现状开放信息需另行核验",
            evidence=_map_evidence(feature.evidence_ids, evidence_records),
            review_status=feature.review_status,
            release_id=feature.release_id,
            record_kind="corpus",
            start_year=start_year,
            end_year=end_year,
        )

    @staticmethod
    def _event(event, point_id: str, evidence_records: dict, entities: dict | None = None) -> TimelineEventOut:  # noqa: ANN001
        start = _historical_year(event.start_time)
        end = _historical_year(event.end_time)
        featured = event.event_type == "imperial_visit" or event.id == "fuxianzhi-event-fan-fuxue"
        certainty = event.time_certainty.value
        return TimelineEventOut(
            id=event.id,
            title=event.title,
            year_start=start,
            year_end=end or start,
            time_label=event.start_time or "年代待考",
            precision="exact" if certainty == "exact" else "period" if certainty == "approximate" else "unknown",
            point_id=point_id,
            summary=event.summary or "府县志事件记录。",
            evidence=_map_evidence(event.evidence_ids, evidence_records),
            review_status=event.review_status,
            release_id=event.release_id,
            record_kind="corpus",
            featured=featured,
            importance="landmark" if featured else "context",
            participants=tuple(
                MapEntityReferenceOut(
                    id=participant_id,
                    name=entities[participant_id].canonical_name,
                    entity_type=entities[participant_id].entity_type.value,
                )
                for participant_id in event.participant_entity_ids
                if entities and participant_id in entities
            ),
        )


async def build_release_map_manifest(release) -> dict:  # noqa: ANN001
    """Build the map body that will be persisted for one release.

    This deliberately reads release-scoped database records. It does not use
    the development ``CATALOG`` constant, so a release's map hash describes
    the exact body later served by the map API.
    """
    from deerflow.persistence.engine import get_session_factory

    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("release map preparation requires a SQL database")
    catalog = await _SqlVersionedCatalogSource(session_factory).build_live_catalog(release)
    return catalog.model_dump(mode="json")


def _place_time_bounds(events: tuple) -> dict[str, tuple[int | None, int | None]]:
    bounds: dict[str, tuple[int | None, int | None]] = {}
    for event in events:
        if not event.place_entity_id:
            continue
        start = _historical_year(event.start_time)
        end = _historical_year(event.end_time)
        if start is None:
            continue
        previous_start, previous_end = bounds.get(event.place_entity_id, (None, None))
        merged_end = (
            end
            if previous_end is None
            else previous_end
            if end is None
            else max(previous_end, end)
        )
        bounds[event.place_entity_id] = (
            start if previous_start is None else min(previous_start, start),
            merged_end,
        )
    return bounds


def _map_relations(relations: tuple, entities: dict, evidence_records: dict) -> tuple[MapRelationOut, ...]:  # noqa: ANN001
    output: list[MapRelationOut] = []
    for relation in relations:
        subject = entities.get(relation.subject_id)
        object_entity = entities.get(relation.object_id)
        if subject is None or object_entity is None:
            continue
        output.append(
            MapRelationOut(
                id=relation.id,
                subject_id=relation.subject_id,
                subject_name=subject.canonical_name,
                subject_type=subject.entity_type.value,
                relation_type=relation.relation_type.value,
                object_id=relation.object_id,
                object_name=object_entity.canonical_name,
                object_type=object_entity.entity_type.value,
                start_time=relation.start_time,
                end_time=relation.end_time,
                confidence=relation.confidence,
                evidence=_map_evidence(relation.evidence_ids, evidence_records),
                review_status=relation.review_status,
                release_id=relation.release_id,
                record_kind="corpus",
            )
        )
    return tuple(output)


_PERSON_PLACE_RELATIONS = {
    "born_in": "出生于",
    "lived_in": "居住于",
    "visited": "到访",
    "worked_at": "任职于",
    "studied_at": "求学于",
}


def _derive_person_trajectories(
    *,
    points: tuple[MapPointOut, ...],
    entities: dict,
    events: tuple,
    relations: tuple,
    evidence_records: dict,
) -> tuple[PersonTrajectoryOut, ...]:
    points_by_entity = {point.entity_id: point for point in points}
    activity_by_person: dict[str, list[TrajectoryPointOut]] = {}
    seen_by_person: dict[str, set[tuple[str, int | None, int | None]]] = {}

    def add(person_id: str, node: TrajectoryPointOut) -> None:
        person = entities.get(person_id)
        if person is None or person.entity_type.value != "person":
            return
        key = (node.point_id, node.year_start, node.year_end)
        if key in seen_by_person.setdefault(person_id, set()):
            return
        seen_by_person[person_id].add(key)
        activity_by_person.setdefault(person_id, []).append(node)

    for event in events:
        point = points_by_entity.get(event.place_entity_id)
        if point is None:
            continue
        start = _historical_year(event.start_time)
        end = _historical_year(event.end_time) or start
        evidence = _merge_evidence(
            _map_evidence(event.evidence_ids, evidence_records),
            point.evidence,
        )
        for person_id in event.participant_entity_ids:
            add(
                person_id,
                TrajectoryPointOut(
                    id=f"trajectory-node-{event.id}-{person_id}",
                    point_id=point.id,
                    year_start=start,
                    year_end=end,
                    time_label=event.start_time or "年代待考",
                    label=event.title,
                    confidence=point.confidence,
                    evidence=evidence,
                    review_status=event.review_status,
                    source_record_id=event.id,
                ),
            )

    for relation in relations:
        label = _PERSON_PLACE_RELATIONS.get(relation.relation_type.value)
        point = points_by_entity.get(relation.object_id)
        if label is None or point is None:
            continue
        person = entities.get(relation.subject_id)
        if person is None or person.entity_type.value != "person":
            continue
        start = _historical_year(relation.start_time)
        end = _historical_year(relation.end_time) or start
        add(
            relation.subject_id,
            TrajectoryPointOut(
                id=f"trajectory-node-{relation.id}",
                point_id=point.id,
                year_start=start,
                year_end=end,
                time_label=relation.start_time or "年代待考",
                label=f"{person.canonical_name}{label}{point.name}",
                confidence=point.confidence,
                evidence=_merge_evidence(
                    _map_evidence(relation.evidence_ids, evidence_records),
                    point.evidence,
                ),
                review_status=relation.review_status,
                source_record_id=relation.id,
            ),
        )

    output: list[PersonTrajectoryOut] = []
    for person_id, nodes in activity_by_person.items():
        nodes.sort(
            key=lambda node: (
                node.year_start is None,
                node.year_start or 0,
                node.year_end or 0,
                node.source_record_id or node.id,
            )
        )
        statuses = {node.review_status for node in nodes if node.review_status is not None}
        status = ReviewStatus.DISPUTED if ReviewStatus.DISPUTED in statuses else ReviewStatus.PENDING if ReviewStatus.PENDING in statuses else ReviewStatus.REVIEWED
        person = entities[person_id]
        output.append(
            PersonTrajectoryOut(
                id=f"corpus-trajectory-{person_id}",
                person_id=person_id,
                person_name=person.canonical_name,
                summary=f"依据当前知识版本中的事件与人物—地点关系生成，共 {len(nodes)} 个活动节点。",
                has_uncertain_segments=(len(nodes) > 1 or any(node.confidence is not SpatialConfidence.EXACT for node in nodes) or any(node.year_start is None for node in nodes)),
                disclaimer="节点按文献时间排序，连接线不代表真实行进道路；待复核节点不构成正式史实结论。",
                points=tuple(nodes),
                review_status=status,
                release_id=person.release_id,
                record_kind="corpus",
            )
        )
    output.sort(key=lambda item: (-len(item.points), item.person_name, item.id))
    return tuple(output)


def _merge_evidence(*groups: tuple[MapEvidenceOut, ...]) -> tuple[MapEvidenceOut, ...]:
    merged: dict[str, MapEvidenceOut] = {}
    for group in groups:
        for item in group:
            merged[item.id] = item
    return tuple(merged.values())


_DYNASTY_ALIASES: dict[str, Dynasty] = {
    "春秋": "spring_autumn",
    "晋": "jin",
    "梁": "liang",
    "唐": "tang",
    "宋": "song",
    "明": "ming",
    "清": "qing",
    "近现代": "modern",
    "现代": "modern",
}
_DYNASTY_VALUES = {
    "spring_autumn",
    "jin",
    "liang",
    "tang",
    "song",
    "ming",
    "qing",
    "modern",
}


def _dynasties(value: str | None) -> tuple[Dynasty, ...]:
    if not value:
        return ()
    rows: list[Dynasty] = []
    for item in re.split(r"[,，、/\s]+", value):
        resolved = _DYNASTY_ALIASES.get(item, item if item in _DYNASTY_VALUES else None)
        if resolved is not None and resolved not in rows:
            rows.append(resolved)  # type: ignore[arg-type]
    return tuple(rows)


def _heritage_status(value: str | None) -> HeritageStatus:
    normalized = (value or "").casefold()
    if normalized in {"extant", "现存", "尚存"}:
        return "extant"
    if normalized in {"site", "遗址", "已毁"}:
        return "site"
    return "uncertain"


def _historical_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(?<!\d)(-?\d{1,4})(?!\d)", value)
    return int(match.group(1)) if match else None


def _map_evidence(evidence_ids: tuple[str, ...], records: dict) -> tuple[MapEvidenceOut, ...]:
    output = []
    for evidence_id in evidence_ids:
        record = records.get(evidence_id)
        if record is None:
            continue
        page_label = f"第 {record.chunk.page_start}–{record.chunk.page_end} 页" if record.chunk.page_end != record.chunk.page_start else f"第 {record.chunk.page_start} 页"
        output.append(
            MapEvidenceOut(
                id=evidence_id,
                title=record.document.title,
                publisher=record.document.source_institution,
                url=f"/api/knowledge-search/evidence/{evidence_id}",
                kind="corpus_evidence",
                retrieved_at=(record.document.updated_at or record.document.created_at or datetime.now(UTC)).date().isoformat(),
                note=f"{page_label}；{record.evidence.review_status.value}",
                quote=getattr(record.evidence, "quote", None),
            )
        )
    return tuple(output)


class RouteCoordinateIn(_Model):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    name: str | None = Field(default=None, max_length=255)


class RoutePlanRequest(_Model):
    coordinates: tuple[RouteCoordinateIn, ...] = Field(min_length=2, max_length=12)
    profile: Literal["driving"] = "driving"

    @model_validator(mode="after")
    def distinct_points(self) -> RoutePlanRequest:
        pairs = {(point.lon, point.lat) for point in self.coordinates}
        if len(pairs) < 2:
            raise ValueError("route requires at least two distinct coordinates")
        return self


class RoutePlanOut(_Model):
    profile: Literal["driving"]
    coordinates: tuple[tuple[float, float], ...]
    distance_meters: float | None = None
    duration_seconds: float | None = None
    provider: str
    routing_status: Literal["routed", "unavailable"]
    route_kind: Literal["road", "stop_order"]
    message: str


OSM_MUDU = MapEvidenceOut(
    id="osm-way-1202226767",
    title="木渎古镇 OpenStreetMap 要素",
    publisher="OpenStreetMap contributors",
    url="https://www.openstreetmap.org/way/1202226767",
    kind="current_map",
    note="用于当前地物范围和中心点定位，不证明历史沿革。",
)
OSM_YAN_GARDEN = MapEvidenceOut(
    id="osm-way-1332751496",
    title="严家花园 OpenStreetMap 要素",
    publisher="OpenStreetMap contributors",
    url="https://www.openstreetmap.org/way/1332751496",
    kind="current_map",
    note="用于现状园林位置；历史信息另见文字来源。",
)
OSM_HONGYIN = MapEvidenceOut(
    id="osm-way-1332790397",
    title="虹饮山房 OpenStreetMap 要素",
    publisher="OpenStreetMap contributors",
    url="https://www.openstreetmap.org/way/1332790397",
    kind="current_map",
    note="用于现状园林位置；不单独证明乾隆巡幸细节。",
)
OSM_GUSONG = MapEvidenceOut(
    id="osm-way-1332790395",
    title="古松园 OpenStreetMap 要素",
    publisher="OpenStreetMap contributors",
    url="https://www.openstreetmap.org/way/1332790395",
    kind="current_map",
    note="仅确认当前地图要素，历史说明仍待项目资料复核。",
)
OSM_BANGYAN = MapEvidenceOut(
    id="osm-way-1332790393",
    title="榜眼府第 OpenStreetMap 要素",
    publisher="OpenStreetMap contributors",
    url="https://www.openstreetmap.org/way/1332790393",
    kind="current_map",
    note="仅确认当前地图要素，历史说明仍待项目资料复核。",
)
OSM_MINGYUE = MapEvidenceOut(
    id="osm-way-1332790396",
    title="明月古寺 OpenStreetMap 要素",
    publisher="OpenStreetMap contributors",
    url="https://www.openstreetmap.org/way/1332790396",
    kind="current_map",
    note="用于现状宗教场所位置。",
)
OSM_LINGYAN_TEMPLE = MapEvidenceOut(
    id="osm-way-862890393",
    title="灵岩山寺 OpenStreetMap 要素",
    publisher="OpenStreetMap contributors",
    url="https://www.openstreetmap.org/way/862890393",
    kind="current_map",
    note="用于现状寺院位置；历史沿革另见文字来源。",
)
OSM_YONGAN_CANDIDATE = MapEvidenceOut(
    id="osm-way-1446612379",
    title="严家花园前未命名步行桥 OpenStreetMap 要素",
    publisher="OpenStreetMap contributors",
    url="https://www.openstreetmap.org/way/1446612379",
    kind="current_map",
    note="与文献所述‘严家花园前’位置交叉对应，但 OSM 未标桥名，必须按近似定位展示。",
)
WIKI_MUDU = MapEvidenceOut(
    id="zhwiki-mudu-town",
    title="木渎镇",
    publisher="中文维基百科",
    url="https://zh.wikipedia.org/wiki/%E6%9C%A8%E6%B8%8E%E9%95%87",
    kind="historical_reference",
    note="公开汇编条目，提供景点名称与历史线索；正式研究需追查条目所列原始来源。",
)
WIKI_YAN_GARDEN = MapEvidenceOut(
    id="zhwiki-yan-garden",
    title="严家花园",
    publisher="中文维基百科",
    url="https://zh.wikipedia.org/wiki/%E4%B8%A5%E5%AE%B6%E8%8A%B1%E5%9B%AD",
    kind="historical_reference",
    note="记载其乾隆年间为沈德潜寓所、道光八年改称端园等沿革线索。",
)
WIKI_YONGAN = MapEvidenceOut(
    id="zhwiki-yongan-bridge-mudu",
    title="永安桥（木渎）",
    publisher="中文维基百科",
    url="https://zh.wikipedia.org/wiki/%E6%B0%B8%E5%AE%89%E6%A1%A5_(%E6%9C%A8%E6%B8%8E)",
    kind="historical_reference",
    note="记载桥址在严家花园前、明弘治十年（1497）建及保护状态。",
)
WIKI_LINGYAN_TEMPLE = MapEvidenceOut(
    id="zhwiki-lingyan-temple",
    title="灵岩山寺",
    publisher="中文维基百科",
    url="https://zh.wikipedia.org/wiki/%E7%81%B5%E5%B2%A9%E5%B1%B1%E5%AF%BA",
    kind="historical_reference",
    note="记载东晋建寺、南梁天监二年（503）扩建和现代保护信息。",
)
WIKIDATA_LINGYAN = MapEvidenceOut(
    id="wikidata-q14950537",
    title="灵岩山（Q14950537）",
    publisher="Wikidata contributors",
    url="https://www.wikidata.org/wiki/Q14950537",
    kind="catalog_reference",
    note="用于山体坐标交叉核验；历史叙述仍以可引用文本为准。",
)


POINTS: tuple[MapPointOut, ...] = (
    MapPointOut(
        id="pt-mudu-old-town",
        entity_id="entity-place-mudu-old-town",
        name="木渎古镇",
        entity_type="historic_district",
        lon=120.5067399,
        lat=31.2530116,
        confidence=SpatialConfidence.EXACT,
        basis="OpenStreetMap way 1202226767 的当前地物中心点",
        dynasties=("qing", "modern"),
        heritage_status="extant",
        access_status="public_space",
        summary="木渎历史街区的现状范围中心；此点用于导航浏览，不代表古镇历史边界。",
        address="苏州市吴中区木渎镇山塘街一带",
        evidence=(OSM_MUDU, WIKI_MUDU),
    ),
    MapPointOut(
        id="pt-yan-garden",
        entity_id="entity-garden-yan",
        name="严家花园",
        entity_type="garden",
        lon=120.5044475,
        lat=31.2547028,
        confidence=SpatialConfidence.EXACT,
        basis="OpenStreetMap way 1332751496 的当前地物中心点",
        dynasties=("qing", "modern"),
        heritage_status="extant",
        access_status="ticket_or_hours",
        summary="现存园林。公开条目记载其前身在清乾隆年间为沈德潜寓所，后历称端园、羡园。",
        address="木渎镇山塘街188号一带",
        evidence=(OSM_YAN_GARDEN, WIKI_YAN_GARDEN),
        start_year=1736,
    ),
    MapPointOut(
        id="pt-hongyin",
        entity_id="entity-garden-hongyin",
        name="虹饮山房",
        entity_type="garden",
        lon=120.5071229,
        lat=31.2535504,
        confidence=SpatialConfidence.EXACT,
        basis="OpenStreetMap way 1332790397 的当前地物中心点",
        dynasties=("qing", "modern"),
        heritage_status="extant",
        access_status="ticket_or_hours",
        summary="现存园林。木渎镇公开条目将其列为乾隆南巡相关行宫线索，具体巡幸年份需进一步核验。",
        address="木渎镇山塘街历史街区",
        evidence=(OSM_HONGYIN, WIKI_MUDU),
        start_year=1736,
    ),
    MapPointOut(
        id="pt-gusong-garden",
        entity_id="entity-garden-gusong",
        name="古松园",
        entity_type="garden",
        lon=120.5088972,
        lat=31.2529539,
        confidence=SpatialConfidence.EXACT,
        basis="OpenStreetMap way 1332790395 的当前地物中心点",
        dynasties=("modern",),
        heritage_status="extant",
        access_status="ticket_or_hours",
        summary="当前可定位的园林景点；本目录暂不添加未经核验的营建年代与人物故事。",
        address="木渎镇山塘街历史街区",
        evidence=(OSM_GUSONG,),
    ),
    MapPointOut(
        id="pt-bangyan-mansion",
        entity_id="entity-residence-bangyan",
        name="榜眼府第",
        entity_type="residence",
        lon=120.5110345,
        lat=31.2501758,
        confidence=SpatialConfidence.EXACT,
        basis="OpenStreetMap way 1332790393 的当前地物中心点",
        dynasties=("modern",),
        heritage_status="extant",
        access_status="ticket_or_hours",
        summary="当前可定位的历史建筑景点；人物归属与营建年代等待正式资料入库复核。",
        address="木渎镇胥江社区一带",
        evidence=(OSM_BANGYAN,),
    ),
    MapPointOut(
        id="pt-mingyue-temple",
        entity_id="entity-temple-mingyue",
        name="明月古寺",
        entity_type="temple",
        lon=120.5062006,
        lat=31.2538627,
        confidence=SpatialConfidence.EXACT,
        basis="OpenStreetMap way 1332790396 的当前地物中心点",
        dynasties=("modern",),
        heritage_status="extant",
        access_status="religious_site",
        summary="现状宗教场所；历史沿革暂不作超出公开目录的确定表述。",
        address="木渎镇山塘街",
        evidence=(OSM_MINGYUE, WIKI_MUDU),
    ),
    MapPointOut(
        id="pt-lingyan-temple",
        entity_id="entity-temple-lingyan",
        name="灵岩山寺",
        entity_type="temple",
        lon=120.4971399,
        lat=31.2643302,
        confidence=SpatialConfidence.EXACT,
        basis="OpenStreetMap way 862890393 与 Wikidata Q15921888 坐标交叉核验",
        dynasties=("jin", "liang", "tang", "song", "ming", "qing", "modern"),
        heritage_status="extant",
        access_status="religious_site",
        summary="灵岩山上的佛教寺院。公开条目记载东晋已有建寺活动，南梁天监二年扩建。",
        address="木渎镇灵岩山",
        evidence=(OSM_LINGYAN_TEMPLE, WIKI_LINGYAN_TEMPLE),
        start_year=317,
    ),
    MapPointOut(
        id="pt-lingyan-mountain",
        entity_id="entity-landform-lingyan",
        name="灵岩山",
        entity_type="landform",
        lon=120.497,
        lat=31.2647,
        confidence=SpatialConfidence.EXACT,
        basis="Wikidata Q14950537 的公开坐标",
        dynasties=("spring_autumn", "modern"),
        heritage_status="extant",
        access_status="public_space",
        summary="木渎西侧山体。春秋吴国相关叙述含传说成分，应与现状地理定位分开理解。",
        address="苏州市吴中区木渎镇西侧",
        evidence=(WIKIDATA_LINGYAN, WIKI_LINGYAN_TEMPLE),
    ),
    MapPointOut(
        id="pt-yongan-bridge",
        entity_id="entity-bridge-yongan",
        name="永安桥",
        entity_type="bridge",
        lon=120.5043797,
        lat=31.2540876,
        confidence=SpatialConfidence.APPROXIMATE,
        basis="文字来源称桥在严家花园前；坐标对应 OSM way 1446612379 的未命名步行桥，尚待实地或测绘资料确认",
        dynasties=("ming", "qing", "modern"),
        heritage_status="extant",
        access_status="view_only",
        summary="公开条目记载为明弘治十年（1497）建的花岗岩单孔石拱桥；当前点位为跨来源近似匹配。",
        address="木渎镇山塘街严家花园前",
        evidence=(OSM_YONGAN_CANDIDATE, WIKI_YONGAN),
        start_year=1497,
    ),
)

LAYERS: tuple[MapLayerOut, ...] = (
    MapLayerOut(
        id="osm-current",
        name="OpenStreetMap 现代底图",
        kind="base",
        available=True,
        source_url="https://www.openstreetmap.org/copyright",
        attribution="© OpenStreetMap contributors",
        calibration_note="Web Mercator 现代底图，仅用于现状位置参照。",
        tile_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    ),
    MapLayerOut(
        id="loc-pingjiang-tu-reference",
        name="《平江图》（1229）公开影像参考",
        kind="historical",
        available=False,
        source_url="https://www.loc.gov/item/2003626507/",
        attribution="Library of Congress",
        calibration_note="该图主要表现南宋平江城，不覆盖木渎镇区，且本项目没有合格控制点和校准成果，因此不作为地图叠加层发布。",
    ),
)

EVENTS: tuple[TimelineEventOut, ...] = (
    TimelineEventOut(
        id="event-lingyan-founded",
        title="灵岩山建寺活动",
        year_start=317,
        year_end=420,
        time_label="东晋时期",
        precision="period",
        point_id="pt-lingyan-temple",
        summary="公开条目称东晋司空陆玩曾居灵岩山并建寺，具体年份待更高等级文献复核。",
        evidence=(WIKI_LINGYAN_TEMPLE,),
        featured=True,
        importance="landmark",
    ),
    TimelineEventOut(
        id="event-lingyan-expanded",
        title="扩建秀峰寺",
        year_start=503,
        year_end=503,
        time_label="南梁天监二年（503）",
        precision="exact",
        point_id="pt-lingyan-temple",
        summary="公开条目记载南梁天监二年扩建为秀峰寺。",
        evidence=(WIKI_LINGYAN_TEMPLE,),
        featured=True,
        importance="notable",
    ),
    TimelineEventOut(
        id="event-yongan-built",
        title="永安桥始建",
        year_start=1497,
        year_end=1497,
        time_label="明弘治十年（1497）",
        precision="exact",
        point_id="pt-yongan-bridge",
        summary="公开条目记载傅潮建花岗岩单孔石拱桥。",
        evidence=(WIKI_YONGAN,),
        featured=True,
        importance="landmark",
    ),
    TimelineEventOut(
        id="event-yan-duan-garden",
        title="严家花园前身改称端园",
        year_start=1828,
        year_end=1828,
        time_label="清道光八年（1828）",
        precision="exact",
        point_id="pt-yan-garden",
        summary="沈氏后人出售后，钱照购得并改称端园。",
        evidence=(WIKI_YAN_GARDEN,),
        featured=True,
        importance="notable",
    ),
    TimelineEventOut(
        id="event-lingyan-protected",
        title="灵岩山寺列入苏州市文物保护单位",
        year_start=1982,
        year_end=1982,
        time_label="1982年",
        precision="exact",
        point_id="pt-lingyan-temple",
        summary="公开条目记载其于1982年10月22日被确认为苏州市文物保护单位。",
        evidence=(WIKI_LINGYAN_TEMPLE,),
        featured=True,
        importance="notable",
    ),
)

TRAJECTORIES: tuple[PersonTrajectoryOut, ...] = (
    PersonTrajectoryOut(
        id="trajectory-qianlong-mudu",
        person_id="person-qianlong-emperor",
        person_name="乾隆帝",
        summary="公开资料可确认木渎御码头与虹饮山房均有乾隆南巡关联，但不能据此复原某一次巡幸的精确路线。",
        has_uncertain_segments=True,
        disclaimer="节点按公开条目列示，年份仅取六次南巡的大致区间；虚线不表示真实行进道路或先后顺序。",
        points=(
            TrajectoryPointOut(
                id="trajectory-qianlong-wharf",
                point_id="pt-mudu-old-town",
                year_start=1751,
                year_end=1784,
                time_label="乾隆南巡时期（1751—1784）",
                label="御码头线索，仅定位到木渎古镇范围",
                confidence=SpatialConfidence.SPECULATIVE,
                evidence=(WIKI_MUDU,),
            ),
            TrajectoryPointOut(
                id="trajectory-qianlong-hongyin",
                point_id="pt-hongyin",
                year_start=1751,
                year_end=1784,
                time_label="乾隆南巡时期（1751—1784）",
                label="虹饮山房关联线索",
                confidence=SpatialConfidence.APPROXIMATE,
                evidence=(WIKI_MUDU, OSM_HONGYIN),
            ),
        ),
    ),
)

ROUTES: tuple[StudyRouteOut, ...] = (
    StudyRouteOut(
        id="route-shantang-gardens",
        name="山塘街园林与桥梁半日研学",
        duration="half_day",
        audience="中学生、公众访学",
        summary="从严家花园出发，经近似定位的永安桥、明月古寺、虹饮山房和古松园，观察园林、水巷与历史街区关系。",
        stop_ids=("pt-yan-garden", "pt-yongan-bridge", "pt-mingyue-temple", "pt-hongyin", "pt-gusong-garden"),
        disclaimer="路线仅为研学内容顺序，不提供实时导航。票务、开放时间和宗教场所参访规则须在出发前向运营方核验；永安桥坐标为近似点。",
        evidence=(OSM_YAN_GARDEN, WIKI_YONGAN, OSM_MINGYUE, OSM_HONGYIN, OSM_GUSONG),
    ),
    StudyRouteOut(
        id="route-lingyan-and-mudu",
        name="灵岩山与木渎历史一日研学",
        duration="full_day",
        audience="高校课程、文史爱好者",
        summary="上午考察灵岩山与灵岩山寺，下午进入木渎古镇，对读山水格局、宗教空间与园林街区。",
        stop_ids=("pt-lingyan-mountain", "pt-lingyan-temple", "pt-yan-garden", "pt-hongyin", "pt-mudu-old-town"),
        disclaimer="路线不承诺交通、体力难度和开放状态；灵岩山春秋叙述含传说成分，应在讲解中明确区分史实与传说。",
        evidence=(WIKIDATA_LINGYAN, WIKI_LINGYAN_TEMPLE, WIKI_YAN_GARDEN, WIKI_MUDU),
    ),
)

CATALOG = MapCatalogOut(
    updated_at="2026-07-29",
    data_notice=(
        "精确点坐标仅描述当前可定位对象；非精确古地点以不确定范围或史料范围显示，"
        "中心仅用于检索与交互，不代表历史精确坐标。范围颜色不表示统计概率。"
        "历史属性来自公开二手条目，所有资料均应在正式发布前回查原始文献和现场测绘成果。"
    ),
    points=POINTS,
    layers=LAYERS,
    events=EVENTS,
    trajectories=TRAJECTORIES,
    routes=ROUTES,
)


def _confidence_rank(value: SpatialConfidence) -> int:
    return {
        SpatialConfidence.SPECULATIVE: 1,
        SpatialConfidence.APPROXIMATE: 2,
        SpatialConfidence.EXACT: 3,
    }[value]


@router.get("/catalog", response_model=MapCatalogOut)
async def get_map_catalog(
    source: VersionedCatalogSource | None = Depends(get_versioned_catalog_source),
) -> MapCatalogOut:
    return await _merged_catalog(source)


async def _merged_catalog(source: VersionedCatalogSource | None) -> MapCatalogOut:
    if source is None:
        return CATALOG
    try:
        versioned = await source.load()
    except MapCatalogSnapshotUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "map_snapshot_unavailable",
                "message": str(exc),
                "retryable": True,
            },
        ) from exc
    if versioned is not None:
        return versioned
    return MapCatalogOut(
        updated_at="unpublished",
        data_notice="当前没有 active 知识版本，地图目录为空。",
        points=(),
        layers=(),
        events=(),
        trajectories=(),
        routes=(),
    )


@router.get("/points", response_model=list[MapPointOut])
async def list_map_points(
    entity_type: list[str] = Query(default=[]),
    dynasty: list[Dynasty] = Query(default=[]),
    min_confidence: SpatialConfidence | None = Query(default=None),
    heritage_status: list[HeritageStatus] = Query(default=[]),
    query: str | None = Query(default=None, max_length=100),
    year: int | None = Query(default=None, ge=-1000, le=2200),
    include_unknown_time: bool = Query(default=True),
    source: VersionedCatalogSource | None = Depends(get_versioned_catalog_source),
) -> list[MapPointOut]:
    catalog = await _merged_catalog(source)
    normalized_query = query.strip().casefold() if query else ""
    rows: list[MapPointOut] = []
    for point in catalog.points:
        if entity_type and point.entity_type not in entity_type:
            continue
        if dynasty and not set(dynasty).intersection(point.dynasties):
            continue
        if min_confidence and _confidence_rank(point.confidence) < _confidence_rank(min_confidence):
            continue
        if heritage_status and point.heritage_status not in heritage_status:
            continue
        if normalized_query and normalized_query not in f"{point.name} {point.summary} {point.address}".casefold():
            continue
        if year is not None:
            if point.start_year is None:
                if not include_unknown_time:
                    continue
            elif year < point.start_year or (point.end_year is not None and year > point.end_year):
                continue
        rows.append(point)
    return rows


@router.get("/layers", response_model=list[MapLayerOut])
async def list_map_layers(
    source: VersionedCatalogSource | None = Depends(get_versioned_catalog_source),
) -> list[MapLayerOut]:
    return list((await _merged_catalog(source)).layers)


@router.get("/events", response_model=list[TimelineEventOut])
async def list_map_events(
    year_start: int | None = Query(default=None, ge=-1000, le=2200),
    year_end: int | None = Query(default=None, ge=-1000, le=2200),
    source: VersionedCatalogSource | None = Depends(get_versioned_catalog_source),
) -> list[TimelineEventOut]:
    rows = list((await _merged_catalog(source)).events)
    if year_start is not None:
        rows = [row for row in rows if row.year_end is None or row.year_end >= year_start]
    if year_end is not None:
        rows = [row for row in rows if row.year_start is None or row.year_start <= year_end]
    return rows


@router.get("/trajectories", response_model=list[PersonTrajectoryOut])
async def list_person_trajectories(
    source: VersionedCatalogSource | None = Depends(get_versioned_catalog_source),
) -> list[PersonTrajectoryOut]:
    return list((await _merged_catalog(source)).trajectories)


@router.get("/routes", response_model=list[StudyRouteOut])
async def list_study_routes(
    duration: Literal["half_day", "full_day"] | None = None,
    source: VersionedCatalogSource | None = Depends(get_versioned_catalog_source),
) -> list[StudyRouteOut]:
    return [route for route in (await _merged_catalog(source)).routes if duration is None or route.duration == duration]


_ROUTE_CACHE: OrderedDict[str, tuple[float, RoutePlanOut]] = OrderedDict()
_ROUTE_INFLIGHT: dict[str, asyncio.Task[RoutePlanOut]] = {}
_ROUTE_LOCK = asyncio.Lock()
_ROUTE_REQUEST_TIMES: list[float] = []


def _routing_number(name: str, default: float, *, minimum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value >= minimum else default


def _route_cache_key(body: RoutePlanRequest, resolved_base: str) -> str:
    return json.dumps(
        {
            "provider": resolved_base,
            "profile": body.profile,
            "coordinates": [[round(point.lon, 7), round(point.lat, 7)] for point in body.coordinates],
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _direct_route(body: RoutePlanRequest, provider: str, message: str) -> RoutePlanOut:
    return RoutePlanOut(
        profile=body.profile,
        coordinates=tuple((point.lon, point.lat) for point in body.coordinates),
        provider=provider,
        routing_status="unavailable",
        route_kind="stop_order",
        message=message,
    )


async def _fetch_osrm_route(
    body: RoutePlanRequest,
    *,
    client: httpx.AsyncClient | None = None,
    resolved_base: str,
) -> RoutePlanOut:
    coordinate_path = ";".join(f"{point.lon:.7f},{point.lat:.7f}" for point in body.coordinates)
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(12.0))
    try:
        response = await http.get(
            f"{resolved_base}/route/v1/{body.profile}/{coordinate_path}",
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
        )
        response.raise_for_status()
        payload = response.json()
        routes = payload.get("routes") if isinstance(payload, dict) else None
        route = routes[0] if isinstance(routes, list) and routes else None
        geometry = route.get("geometry") if isinstance(route, dict) else None
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError("routing provider returned no route geometry")
        return RoutePlanOut(
            profile=body.profile,
            coordinates=tuple((float(item[0]), float(item[1])) for item in coordinates),
            distance_meters=float(route["distance"]),
            duration_seconds=float(route["duration"]),
            provider=resolved_base,
            routing_status="routed",
            route_kind="road",
            message="Road route calculated successfully.",
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return _direct_route(
            body,
            resolved_base,
            message="Routing service is unavailable; showing stop order as a direct line, not road navigation.",
        )
    finally:
        if owns_client:
            await http.aclose()


async def fetch_osrm_route(
    body: RoutePlanRequest,
    *,
    client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
) -> RoutePlanOut:
    resolved_base = (base_url or os.getenv("XINGXI_ROUTING_BASE_URL") or "https://router.project-osrm.org").rstrip("/")
    # Tests and callers with an injected client own the transport and bypass
    # the process cache/rate limiter. Gateway requests use the shared path.
    if client is not None:
        return await _fetch_osrm_route(body, client=client, resolved_base=resolved_base)

    cache_key = _route_cache_key(body, resolved_base)
    now = time.monotonic()
    async with _ROUTE_LOCK:
        cached = _ROUTE_CACHE.get(cache_key)
        if cached is not None:
            expires_at, result = cached
            if expires_at > now:
                _ROUTE_CACHE.move_to_end(cache_key)
                return result
            _ROUTE_CACHE.pop(cache_key, None)

        pending = _ROUTE_INFLIGHT.get(cache_key)
        if pending is None:
            window_start = now - 60.0
            _ROUTE_REQUEST_TIMES[:] = [timestamp for timestamp in _ROUTE_REQUEST_TIMES if timestamp > window_start]
            max_requests = int(_routing_number("XINGXI_ROUTING_MAX_REQUESTS_PER_MINUTE", 60, minimum=1))
            if len(_ROUTE_REQUEST_TIMES) >= max_requests:
                result = _direct_route(
                    body,
                    resolved_base,
                    "Routing request limit reached; showing stop order as a direct line, not road navigation.",
                )
                _ROUTE_CACHE[cache_key] = (
                    now + _routing_number("XINGXI_ROUTING_FAILURE_CACHE_TTL_SECONDS", 15, minimum=1),
                    result,
                )
                return result
            _ROUTE_REQUEST_TIMES.append(now)
            pending = asyncio.create_task(
                _fetch_osrm_route(body, resolved_base=resolved_base)
            )
            _ROUTE_INFLIGHT[cache_key] = pending
            leader = True
        else:
            leader = False

    try:
        result = await asyncio.shield(pending)
        if leader:
            ttl_name = (
                "XINGXI_ROUTING_CACHE_TTL_SECONDS"
                if result.routing_status == "routed"
                else "XINGXI_ROUTING_FAILURE_CACHE_TTL_SECONDS"
            )
            async with _ROUTE_LOCK:
                _ROUTE_CACHE[cache_key] = (
                    time.monotonic() + _routing_number(ttl_name, 900 if result.routing_status == "routed" else 15, minimum=1),
                    result,
                )
                max_entries = int(_routing_number("XINGXI_ROUTING_CACHE_MAX_ENTRIES", 256, minimum=1))
                while len(_ROUTE_CACHE) > max_entries:
                    _ROUTE_CACHE.popitem(last=False)
        return result
    finally:
        if leader:
            async with _ROUTE_LOCK:
                if _ROUTE_INFLIGHT.get(cache_key) is pending:
                    _ROUTE_INFLIGHT.pop(cache_key, None)


@router.post("/route-plan", response_model=RoutePlanOut)
async def plan_map_route(body: RoutePlanRequest, request: Request) -> RoutePlanOut:
    await get_current_user_from_request(request)
    try:
        return await fetch_osrm_route(body)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Routing service failed") from exc
