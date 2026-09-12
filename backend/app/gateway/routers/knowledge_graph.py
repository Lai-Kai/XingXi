from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from wu_culture.aliases import NameAuthorityRequest, NameAuthorityResolution, NameAuthorityService
from wu_culture.entities import EntityCreate, EntityService
from wu_culture.events import EventCreate, EventRecord
from wu_culture.extraction import KnowledgeExtractionResult, extract_knowledge
from wu_culture.geo import GeoFeature, SpatialConfidence
from wu_culture.gloss import GlossResult, gloss_passage
from wu_culture.graph import PersistentGraphQueryService
from wu_culture.models import ReviewStatus
from wu_culture.relations import RelationCreate, RelationRecord

from app.gateway.deps import get_current_user_from_request, require_admin_user
from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.wu_culture import (
    SqlEventRepository,
    SqlEvidenceRepository,
    SqlGeoRepository,
    SqlKnowledgeGraphRepository,
)

router = APIRouter(prefix="/api/knowledge-graph", tags=["knowledge-graph"])
_ADMIN_DETAIL = "Administrator privileges are required to manage knowledge graph data"


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=20_000)
    evidence_ids: tuple[str, ...] = ()
    persist: bool = False


class ExtractionResponse(BaseModel):
    extraction: KnowledgeExtractionResult
    entity_ids: dict[str, str] = {}
    relation_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    alias_notice: str | None = None


class ReviewStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: ReviewStatus


class GlossLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=10_000)
    title: str = Field(default="古文释读展签", min_length=1, max_length=120)
    object_name: str | None = Field(default=None, max_length=120)
    source_title: str | None = Field(default=None, max_length=255)
    volume: str | None = Field(default=None, max_length=120)
    page: str | None = Field(default=None, max_length=60)
    max_chars: int = Field(default=2_000, ge=1, le=10_000)


class GlossLabelResponse(BaseModel):
    title: str
    object_name: str | None
    source_title: str | None
    volume: str | None
    page: str | None
    status: str = "reading_aid"
    status_label: str = "阅读辅助，待人工校注"
    gloss: GlossResult


def get_graph_repository() -> SqlKnowledgeGraphRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Knowledge graph requires a SQL database")
    return SqlKnowledgeGraphRepository(session_factory)


def get_event_repository() -> SqlEventRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Timeline requires a SQL database")
    return SqlEventRepository(session_factory)


def get_geo_repository() -> SqlGeoRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Map features require a SQL database")
    return SqlGeoRepository(session_factory)


def get_entity_service() -> EntityService:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Entity extraction requires a SQL database")
    from deerflow.persistence.wu_culture import SqlEntityRepository

    return EntityService(SqlEntityRepository(session_factory))


def get_evidence_repository() -> SqlEvidenceRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Name authority resolution requires a SQL database")
    return SqlEvidenceRepository(session_factory)


async def _resolve_active_release_id(release_id: str | None) -> str | None:
    """Keep graph reads pinned to the active, evidence-backed corpus."""
    if release_id is not None:
        return release_id
    session_factory = get_session_factory()
    if session_factory is None:
        return None
    from deerflow.persistence.wu_culture import SqlKnowledgeReleaseRepository

    release = await SqlKnowledgeReleaseRepository(session_factory).get_active_summary()
    return release.id if release is not None else None


@router.post("/aliases/resolve-authority", response_model=NameAuthorityResolution)
async def resolve_alias_authority(
    body: NameAuthorityRequest,
    request: Request,
    repository: SqlEvidenceRepository = Depends(get_evidence_repository),
) -> NameAuthorityResolution:
    await get_current_user_from_request(request)
    return await NameAuthorityService(repository).resolve(body)


@router.post("/gloss", response_model=GlossLabelResponse)
async def create_gloss_label(
    body: GlossLabelRequest,
    request: Request,
) -> GlossLabelResponse:
    await get_current_user_from_request(request)
    try:
        gloss = gloss_passage(body.text, max_chars=body.max_chars)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GlossLabelResponse(
        title=body.title,
        object_name=body.object_name,
        source_title=body.source_title,
        volume=body.volume,
        page=body.page,
        gloss=gloss,
    )


@router.post("/extract", response_model=ExtractionResponse)
async def extract_text_knowledge(
    body: ExtractionRequest,
    request: Request,
    entity_service: EntityService = Depends(get_entity_service),
    graph_repository: SqlKnowledgeGraphRepository = Depends(get_graph_repository),
    event_repository: SqlEventRepository = Depends(get_event_repository),
) -> ExtractionResponse:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    extraction = extract_knowledge(body.text)
    if not body.persist:
        return ExtractionResponse(extraction=extraction)
    if not body.evidence_ids:
        raise HTTPException(
            status_code=400,
            detail="持久化抽取结果前必须绑定文献 Evidence；无证据文本只能预览。",
        )
    if len(body.evidence_ids) != len(set(body.evidence_ids)):
        raise HTTPException(status_code=400, detail="evidence_ids 必须唯一")
    evidence_locators = await graph_repository.evidence_locators(body.evidence_ids)
    found_evidence_ids = {str(item["evidence_id"]) for item in evidence_locators}
    missing_evidence_ids = [item for item in body.evidence_ids if item not in found_evidence_ids]
    if missing_evidence_ids:
        raise HTTPException(
            status_code=400,
            detail=f"无法绑定 Evidence：{missing_evidence_ids[0]}",
        )

    entity_ids: dict[str, str] = {}
    try:
        for candidate in extraction.entities:
            matches = await graph_repository.resolve_entities(candidate.name, limit=10)
            exact = next((item for item in matches if item.canonical_name.casefold() == candidate.name.casefold()), None)
            if exact is None:
                exact = await entity_service.create(
                    EntityCreate(
                        canonical_name=candidate.name,
                        entity_type=candidate.entity_type,
                        summary=f"自动抽取待复核：{candidate.reason}",
                        evidence_ids=body.evidence_ids,
                        review_status=ReviewStatus.PENDING,
                    )
                )
            entity_ids[candidate.name] = exact.id

        relation_ids: list[str] = []
        for candidate in extraction.relations:
            record = await graph_repository.create_relation(
                RelationCreate(
                    subject_id=entity_ids[candidate.subject_name],
                    relation_type=candidate.relation_type,
                    object_id=entity_ids[candidate.object_name],
                    confidence=0.65 if body.evidence_ids else 0.45,
                    evidence_ids=body.evidence_ids,
                    is_inferred=not body.evidence_ids,
                    review_status=ReviewStatus.PENDING,
                )
            )
            relation_ids.append(record.id)

        event_ids: list[str] = []
        for candidate in extraction.events:
            record = await event_repository.create(
                EventCreate(
                    title=candidate.title,
                    event_type="text_extraction",
                    start_time=candidate.start_time,
                    time_certainty=candidate.time_certainty,
                    place_entity_id=entity_ids.get(candidate.place_name or ""),
                    summary=f"自动抽取待复核：{candidate.source_text}",
                    evidence_ids=body.evidence_ids,
                    is_inferred=not body.evidence_ids,
                    review_status=ReviewStatus.PENDING,
                )
            )
            event_ids.append(record.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ExtractionResponse(
        extraction=extraction,
        entity_ids=entity_ids,
        relation_ids=tuple(relation_ids),
        event_ids=tuple(event_ids),
        alias_notice=("Alias candidates were extracted but remain unindexed until they are evidence-bound, reviewed, and attached to a knowledge release." if extraction.aliases else None),
    )


@router.get("/query")
async def query_graph(
    request: Request,
    entity: str = Query(min_length=1, max_length=255),
    max_depth: int = Query(default=2, ge=1, le=3),
    max_nodes: int = Query(default=120, ge=1, le=200),
    relation_types: list[str] | None = Query(default=None),
    release_id: str | None = Query(default=None, max_length=255),
    repository: SqlKnowledgeGraphRepository = Depends(get_graph_repository),
) -> dict:
    await get_current_user_from_request(request)
    release_id = await _resolve_active_release_id(release_id)
    result = await PersistentGraphQueryService(repository).query(
        entity=entity,
        max_depth=max_depth,
        max_nodes=max_nodes,
        relation_types=relation_types,
        release_id=release_id,
    )
    return {**result, "release_id": release_id, "max_depth": max_depth, "max_nodes": max_nodes}


@router.get("/relations", response_model=list[RelationRecord])
async def list_relations(
    request: Request,
    entity_id: str | None = Query(default=None, max_length=255),
    relation_types: list[str] | None = Query(default=None),
    release_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=100, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    repository: SqlKnowledgeGraphRepository = Depends(get_graph_repository),
) -> list[RelationRecord]:
    await get_current_user_from_request(request)
    release_id = await _resolve_active_release_id(release_id)
    return await repository.list_relations(
        entity_id=entity_id,
        relation_types=relation_types,
        release_id=release_id,
        limit=limit,
        offset=offset,
    )


@router.post("/relations", response_model=RelationRecord, status_code=201)
async def create_relation(
    body: RelationCreate,
    request: Request,
    repository: SqlKnowledgeGraphRepository = Depends(get_graph_repository),
) -> RelationRecord:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    try:
        return await repository.create_relation(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/relations/{relation_id}", status_code=204)
async def delete_relation(
    relation_id: str,
    request: Request,
    repository: SqlKnowledgeGraphRepository = Depends(get_graph_repository),
) -> None:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    if not await repository.delete_relation(relation_id):
        raise HTTPException(status_code=404, detail="Relation not found")


@router.patch("/relations/{relation_id}/review", response_model=RelationRecord)
async def review_relation(
    relation_id: str,
    body: ReviewStatusUpdate,
    request: Request,
    repository: SqlKnowledgeGraphRepository = Depends(get_graph_repository),
) -> RelationRecord:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    try:
        return await repository.review_relation(relation_id, body.review_status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Relation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/events", response_model=list[EventRecord])
async def list_events(
    request: Request,
    place_entity_id: str | None = Query(default=None, max_length=255),
    participant_entity_id: str | None = Query(default=None, max_length=255),
    event_type: str | None = Query(default=None, max_length=64),
    release_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=100, ge=1, le=200),
    repository: SqlEventRepository = Depends(get_event_repository),
) -> list[EventRecord]:
    await get_current_user_from_request(request)
    release_id = await _resolve_active_release_id(release_id)
    return await repository.list(
        place_entity_id=place_entity_id,
        participant_entity_id=participant_entity_id,
        event_type=event_type,
        release_id=release_id,
        limit=limit,
    )


@router.post("/events", response_model=EventRecord, status_code=201)
async def create_event(
    body: EventCreate,
    request: Request,
    repository: SqlEventRepository = Depends(get_event_repository),
) -> EventRecord:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    try:
        return await repository.create(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    request: Request,
    repository: SqlEventRepository = Depends(get_event_repository),
) -> None:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    if not await repository.delete(event_id):
        raise HTTPException(status_code=404, detail="Event not found")


@router.patch("/events/{event_id}/review", response_model=EventRecord)
async def review_event(
    event_id: str,
    body: ReviewStatusUpdate,
    request: Request,
    repository: SqlEventRepository = Depends(get_event_repository),
) -> EventRecord:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    try:
        return await repository.review(event_id, body.review_status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/geo", response_model=list[GeoFeature])
async def list_geo_features(
    request: Request,
    entity_ids: list[str] | None = Query(default=None),
    min_confidence: SpatialConfidence | None = Query(default=None),
    release_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=200, ge=1, le=500),
    repository: SqlGeoRepository = Depends(get_geo_repository),
) -> list[GeoFeature]:
    await get_current_user_from_request(request)
    release_id = await _resolve_active_release_id(release_id)
    return await repository.list(
        entity_ids=entity_ids,
        min_confidence=min_confidence,
        release_id=release_id,
        limit=limit,
    )


@router.put("/geo/{entity_id}", response_model=GeoFeature)
async def upsert_geo_feature(
    entity_id: str,
    body: GeoFeature,
    request: Request,
    repository: SqlGeoRepository = Depends(get_geo_repository),
) -> GeoFeature:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    if body.entity_id != entity_id:
        raise HTTPException(status_code=400, detail="Path entity_id must match request body entity_id")
    try:
        return await repository.upsert(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/geo/{entity_id}", status_code=204)
async def delete_geo_feature(
    entity_id: str,
    request: Request,
    repository: SqlGeoRepository = Depends(get_geo_repository),
) -> None:
    await require_admin_user(request, detail=_ADMIN_DETAIL)
    if not await repository.delete(entity_id):
        raise HTTPException(status_code=404, detail="Map feature not found")
