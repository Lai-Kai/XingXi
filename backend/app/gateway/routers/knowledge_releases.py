from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from wu_culture.releases import (
    ActivateReleaseRequest,
    KnowledgeRelease,
    KnowledgeReleaseConflict,
    KnowledgeReleaseEvent,
    KnowledgeReleaseGateError,
    KnowledgeReleaseNotFound,
    KnowledgeReleasePreparationError,
    KnowledgeReleaseRepository,
    KnowledgeReleaseState,
    PublishReleaseRequest,
    RetryReleaseRequest,
    RollbackReleaseRequest,
)

from app.gateway.deps import require_business_capability
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/knowledge-releases", tags=["knowledge-releases"])
_ADMIN_REQUIRED_DETAIL = "Admin privileges are required to manage knowledge releases"


def get_knowledge_release_repository() -> KnowledgeReleaseRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Knowledge releases require a SQL database")
    from app.gateway.routers.map_points import build_release_map_manifest
    from deerflow.persistence.operations import OperationsRepository
    from deerflow.persistence.wu_culture import SqlFullTextRepository, SqlKnowledgeReleaseRepository

    return SqlKnowledgeReleaseRepository(
        session_factory,
        publication_indexer=SqlFullTextRepository(session_factory),
        publication_assets=OperationsRepository(
            session_factory,
            publication_map_manifest_factory=build_release_map_manifest,
        ),
    )


async def _admin_id(request: Request) -> str:
    user = await require_business_capability(request, "release:approve", detail=_ADMIN_REQUIRED_DETAIL)
    return str(user.id)


@router.get("", response_model=list[KnowledgeRelease])
async def list_knowledge_releases(request: Request, repository: KnowledgeReleaseRepository = Depends(get_knowledge_release_repository)) -> list[KnowledgeRelease]:
    await _admin_id(request)
    return await repository.list_releases()


@router.get("/state", response_model=KnowledgeReleaseState)
async def get_knowledge_release_state(request: Request, repository: KnowledgeReleaseRepository = Depends(get_knowledge_release_repository)) -> KnowledgeReleaseState:
    await _admin_id(request)
    return await repository.get_state()


@router.get("/events", response_model=list[KnowledgeReleaseEvent])
async def list_knowledge_release_events(request: Request, repository: KnowledgeReleaseRepository = Depends(get_knowledge_release_repository)) -> list[KnowledgeReleaseEvent]:
    await _admin_id(request)
    return await repository.list_events()


@router.get("/{release_id}", response_model=KnowledgeRelease)
async def get_knowledge_release(release_id: str, request: Request, repository: KnowledgeReleaseRepository = Depends(get_knowledge_release_repository)) -> KnowledgeRelease:
    await _admin_id(request)
    release = await repository.get(release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Knowledge release not found")
    return release


@router.post("", response_model=KnowledgeRelease, status_code=201)
async def publish_knowledge_release(body: PublishReleaseRequest, request: Request, repository: KnowledgeReleaseRepository = Depends(get_knowledge_release_repository)) -> KnowledgeRelease:
    admin_id = await _admin_id(request)
    try:
        return await repository.publish(body, actor_id=admin_id, created_at=datetime.now(UTC))
    except KnowledgeReleaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KnowledgeReleaseGateError as exc:
        raise HTTPException(status_code=409, detail={"code": "release_gate_blocked", "message": str(exc)}) from exc
    except (KnowledgeReleaseGateError, KnowledgeReleaseConflict) as exc:
        raise HTTPException(status_code=409, detail={"code": "release_conflict", "message": str(exc)}) from exc
    except KnowledgeReleasePreparationError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "release_preparation_failed",
                "message": str(exc),
                "release_id": exc.release_id,
                "retryable": True,
            },
        ) from exc


@router.post("/{release_id}/retry", response_model=KnowledgeRelease)
async def retry_knowledge_release(
    release_id: str,
    body: RetryReleaseRequest,
    request: Request,
    repository: KnowledgeReleaseRepository = Depends(get_knowledge_release_repository),
) -> KnowledgeRelease:
    admin_id = await _admin_id(request)
    try:
        return await repository.retry(
            release_id,
            body,
            actor_id=admin_id,
            changed_at=datetime.now(UTC),
        )
    except KnowledgeReleaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KnowledgeReleaseGateError, KnowledgeReleaseConflict) as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "release_retry_blocked", "message": str(exc)},
        ) from exc
    except KnowledgeReleasePreparationError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "release_preparation_failed",
                "message": str(exc),
                "release_id": exc.release_id,
                "retryable": True,
            },
        ) from exc


@router.post("/activate", response_model=KnowledgeReleaseState)
async def activate_knowledge_release(body: ActivateReleaseRequest, request: Request, repository: KnowledgeReleaseRepository = Depends(get_knowledge_release_repository)) -> KnowledgeReleaseState:
    admin_id = await _admin_id(request)
    try:
        return await repository.activate(body, actor_id=admin_id, changed_at=datetime.now(UTC))
    except KnowledgeReleaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KnowledgeReleaseGateError, KnowledgeReleaseConflict) as exc:
        raise HTTPException(status_code=409, detail={"code": "release_conflict", "message": str(exc)}) from exc


@router.post("/rollback", response_model=KnowledgeReleaseState)
async def rollback_knowledge_release(body: RollbackReleaseRequest, request: Request, repository: KnowledgeReleaseRepository = Depends(get_knowledge_release_repository)) -> KnowledgeReleaseState:
    admin_id = await _admin_id(request)
    try:
        return await repository.rollback(body, actor_id=admin_id, changed_at=datetime.now(UTC))
    except KnowledgeReleaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KnowledgeReleaseGateError, KnowledgeReleaseConflict) as exc:
        raise HTTPException(status_code=409, detail={"code": "release_conflict", "message": str(exc)}) from exc
