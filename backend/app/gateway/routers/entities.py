from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from wu_culture.entities import (
    EntityCreate,
    EntityDetail,
    EntityInUseError,
    EntityRecord,
    EntityService,
    EntityUpdate,
    EntityValidationError,
)
from wu_culture.models import EntityType, ReviewStatus

from app.gateway.deps import get_current_user_from_request, require_admin_user
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/entities", tags=["entities"])


def get_entity_service() -> EntityService:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Entity API requires a SQL database")
    from deerflow.persistence.wu_culture import SqlEntityRepository

    return EntityService(SqlEntityRepository(session_factory))


async def _resolve_active_release_id(release_id: str | None) -> str | None:
    if release_id is not None:
        return release_id
    from deerflow.persistence.wu_culture import SqlKnowledgeReleaseRepository

    release = await SqlKnowledgeReleaseRepository(get_session_factory()).get_active_summary()
    return release.id if release is not None else None


@router.get("", response_model=list[EntityRecord])
async def list_entities(
    request: Request,
    entity_type: EntityType | None = None,
    review_status: ReviewStatus | None = None,
    q: str | None = Query(default=None, max_length=200),
    release_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: EntityService = Depends(get_entity_service),
) -> list[EntityRecord]:
    await get_current_user_from_request(request)
    return await service.list_entities(
        entity_type=entity_type,
        review_status=review_status,
        q=q,
        limit=limit,
        offset=offset,
        release_id=await _resolve_active_release_id(release_id),
    )


@router.get("/{entity_id}", response_model=EntityDetail)
async def get_entity(
    entity_id: str,
    request: Request,
    service: EntityService = Depends(get_entity_service),
) -> EntityDetail:
    await get_current_user_from_request(request)
    detail = await service.get_detail(entity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return detail


@router.post("", response_model=EntityRecord, status_code=201)
async def create_entity(
    body: EntityCreate,
    request: Request,
    service: EntityService = Depends(get_entity_service),
) -> EntityRecord:
    await require_admin_user(request, detail="Administrator privileges are required to manage entities")
    try:
        return await service.create(body)
    except EntityValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{entity_id}", response_model=EntityRecord)
async def update_entity(
    entity_id: str,
    body: EntityUpdate,
    request: Request,
    service: EntityService = Depends(get_entity_service),
) -> EntityRecord:
    await require_admin_user(request, detail="Administrator privileges are required to manage entities")
    try:
        return await service.update(entity_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Entity not found") from exc
    except EntityValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{entity_id}", status_code=204)
async def delete_entity(
    entity_id: str,
    request: Request,
    force: bool = Query(default=False),
    service: EntityService = Depends(get_entity_service),
) -> None:
    await require_admin_user(request, detail="Administrator privileges are required to manage entities")
    try:
        await service.delete(entity_id, force=force)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Entity not found") from exc
    except EntityInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
