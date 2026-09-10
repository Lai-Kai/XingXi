from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from wu_culture import AuthorizedUse, evaluate_source_access
from wu_culture.citations.contract import evidence_detail_from_record
from wu_culture.citations.models import EvidenceDetail
from wu_culture.filters import StructuredSearchFilters
from wu_culture.fulltext import FullTextIndexResult, FullTextReleaseNotIndexed, FullTextRepository, FullTextSearchRequest, FullTextSearchResponse
from wu_culture.hybrid import HybridSearchRequest, HybridSearchResponse, HybridSearchService, HybridSearchUnavailable
from wu_culture.ranking import TrustReranker
from wu_culture.structured_search import (
    StructuredSearchCursorError,
    StructuredSearchRequest,
    StructuredSearchResponse,
    StructuredSearchService,
)
from wu_culture.vectors import (
    VectorIndexBuildRequest,
    VectorIndexConflict,
    VectorIndexNotReady,
    VectorIndexState,
    VectorIndexVersion,
    VectorSearchRequest,
    VectorSearchResponse,
)

from app.gateway.deps import get_current_user_from_request, require_admin_user
from deerflow.config.app_config import get_app_config
from deerflow.embeddings import VectorEmbeddingError
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/knowledge-search", tags=["knowledge-search"])


def get_fulltext_repository() -> FullTextRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Full-text search requires a SQL database")
    from deerflow.persistence.wu_culture import SqlFullTextRepository

    return SqlFullTextRepository(session_factory)


def get_vector_repository():  # noqa: ANN201
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Vector search requires a SQL database")
    from deerflow.persistence.wu_culture import SqlVectorRepository

    return SqlVectorRepository(session_factory)


def get_vector_service():  # noqa: ANN201
    from deerflow.embeddings import EmbeddingService, VectorIndexService

    try:
        embeddings = EmbeddingService(get_app_config().embedding)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return VectorIndexService(get_vector_repository(), embeddings)


def get_hybrid_service():  # noqa: ANN201
    from deerflow.embeddings import EmbeddingService, VectorIndexService

    config = get_app_config()
    vectors = None
    if config.embedding.enabled:
        vectors = VectorIndexService(get_vector_repository(), EmbeddingService(config.embedding))
    return HybridSearchService(
        get_fulltext_repository(),
        vectors,
        timeout_seconds=config.hybrid_search.channel_timeout_seconds,
        rrf_k=config.hybrid_search.rrf_k,
        reranker=TrustReranker(config.trust_rerank),
    )


def get_structured_search_service() -> StructuredSearchService:
    from wu_culture.aliases import AsyncAliasExpansionService

    from deerflow.persistence.wu_culture import SqlAliasRepository

    session_factory = get_session_factory()
    alias_expander = AsyncAliasExpansionService(SqlAliasRepository(session_factory)) if session_factory is not None else None
    return StructuredSearchService(get_hybrid_service(), alias_expander)


async def _admin_id(request: Request) -> str:
    await require_admin_user(request, detail="Admin privileges are required to manage vector indexes")
    user = getattr(request.state, "user", None)
    if user is None:
        user = await get_current_user_from_request(request)
    return str(user.id)


async def _authorized_use_for_release(release_id: str | None) -> AuthorizedUse:
    session_factory = get_session_factory()
    if session_factory is None:
        return AuthorizedUse.PUBLIC_QUOTE
    from deerflow.persistence.wu_culture import SqlKnowledgeReleaseRepository

    repository = SqlKnowledgeReleaseRepository(session_factory)
    release = await repository.get(release_id) if release_id else await repository.get_active()
    return AuthorizedUse.INTERNAL_PROCESSING if release is not None and release.scope == "internal" else AuthorizedUse.PUBLIC_QUOTE


async def _authorized_use_for_evidence(evidence_id: str) -> AuthorizedUse:
    session_factory = get_session_factory()
    if session_factory is None:
        return AuthorizedUse.PUBLIC_QUOTE
    from deerflow.persistence.wu_culture import FullTextDocumentRow, KnowledgeReleaseRow

    async with session_factory() as session:
        scope = await session.scalar(
            select(KnowledgeReleaseRow.scope)
            .join(FullTextDocumentRow, FullTextDocumentRow.release_id == KnowledgeReleaseRow.id)
            .where(FullTextDocumentRow.external_id == evidence_id)
        )
    return AuthorizedUse.INTERNAL_PROCESSING if scope == "internal" else AuthorizedUse.PUBLIC_QUOTE


@router.post("/fulltext", response_model=FullTextSearchResponse)
async def search_knowledge_fulltext(
    body: FullTextSearchRequest,
    request: Request,
    repository: FullTextRepository = Depends(get_fulltext_repository),
) -> FullTextSearchResponse:
    await get_current_user_from_request(request)
    public_request = body.model_copy(update={"authorized_use": await _authorized_use_for_release(body.release_id)})
    try:
        return await repository.search(public_request)
    except FullTextReleaseNotIndexed as exc:
        raise HTTPException(status_code=409, detail={"code": "fulltext_release_not_ready", "message": str(exc)}) from exc


@router.post("/fulltext/releases/{release_id}/rebuild", response_model=FullTextIndexResult)
async def rebuild_knowledge_fulltext(
    release_id: str,
    request: Request,
    repository: FullTextRepository = Depends(get_fulltext_repository),
) -> FullTextIndexResult:
    await require_admin_user(request, detail="Admin privileges are required to rebuild full-text indexes")
    try:
        return await repository.rebuild_release(release_id, indexed_at=datetime.now(UTC))
    except FullTextReleaseNotIndexed as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/vector", response_model=VectorSearchResponse)
async def search_knowledge_vectors(
    body: VectorSearchRequest,
    request: Request,
    service=Depends(get_vector_service),  # noqa: B008, ANN001
) -> VectorSearchResponse:
    await get_current_user_from_request(request)
    public_request = body.model_copy(update={"authorized_use": await _authorized_use_for_release(body.release_id)})
    try:
        return await service.search(public_request)
    except (VectorIndexNotReady, VectorIndexConflict) as exc:
        raise HTTPException(status_code=409, detail={"code": "vector_index_not_ready", "message": str(exc)}) from exc
    except VectorEmbeddingError as exc:
        raise HTTPException(status_code=502, detail={"code": "embedding_provider_error", "message": str(exc)}) from exc


@router.post("/vector/rebuild", response_model=VectorIndexVersion)
async def rebuild_knowledge_vectors(
    body: VectorIndexBuildRequest,
    request: Request,
    service=Depends(get_vector_service),  # noqa: B008, ANN001
) -> VectorIndexVersion:
    admin_id = await _admin_id(request)
    try:
        return await service.rebuild(
            body.release_id,
            expected_state_version=body.expected_state_version,
            actor_id=admin_id,
            started_at=datetime.now(UTC),
        )
    except VectorIndexConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "vector_index_conflict", "message": str(exc)}) from exc
    except VectorEmbeddingError as exc:
        raise HTTPException(status_code=502, detail={"code": "embedding_provider_error", "message": str(exc)}) from exc


@router.get("/vector/releases/{release_id}/state", response_model=VectorIndexState)
async def get_vector_index_state(
    release_id: str,
    request: Request,
    repository=Depends(get_vector_repository),  # noqa: B008, ANN001
) -> VectorIndexState:
    await _admin_id(request)
    return await repository.get_state(release_id)


@router.get("/vector/releases/{release_id}/versions", response_model=list[VectorIndexVersion])
async def list_vector_index_versions(
    release_id: str,
    request: Request,
    repository=Depends(get_vector_repository),  # noqa: B008, ANN001
) -> list[VectorIndexVersion]:
    await _admin_id(request)
    return await repository.list_versions(release_id)


@router.post("/hybrid", response_model=HybridSearchResponse)
async def search_knowledge_hybrid(
    body: HybridSearchRequest,
    request: Request,
    service: HybridSearchService = Depends(get_hybrid_service),
) -> HybridSearchResponse:
    await get_current_user_from_request(request)
    public_request = body.model_copy(update={"authorized_use": await _authorized_use_for_release(body.release_id)})
    try:
        return await service.search(public_request)
    except (FullTextReleaseNotIndexed, HybridSearchUnavailable) as exc:
        raise HTTPException(status_code=503, detail={"code": "hybrid_search_unavailable", "message": str(exc)}) from exc


@router.post("/structured", response_model=StructuredSearchResponse)
async def search_knowledge_structured(
    body: StructuredSearchRequest,
    request: Request,
    service: StructuredSearchService = Depends(get_structured_search_service),
) -> StructuredSearchResponse:
    await get_current_user_from_request(request)
    try:
        return await service.search(body.model_copy(update={"authorized_use": await _authorized_use_for_release(body.release_id)}))
    except StructuredSearchCursorError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_search_cursor", "message": str(exc)}) from exc
    except (FullTextReleaseNotIndexed, HybridSearchUnavailable) as exc:
        raise HTTPException(status_code=503, detail={"code": "structured_search_unavailable", "message": str(exc)}) from exc


@router.get("/structured/filters/schema")
async def get_structured_search_filter_schema(request: Request) -> dict:
    await get_current_user_from_request(request)
    return StructuredSearchFilters.model_json_schema()


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetail)
async def get_evidence_detail(
    evidence_id: str,
    request: Request,
) -> EvidenceDetail:
    """Open a single evidence locator for citation deep links."""
    await get_current_user_from_request(request)
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Evidence lookup requires a SQL database")
    from deerflow.persistence.wu_culture import SqlEvidenceRepository

    record = await SqlEvidenceRepository(session_factory).get_evidence(evidence_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "evidence_not_found", "message": f"Evidence {evidence_id!r} was not found"},
        )
    access = evaluate_source_access(record.document, use=await _authorized_use_for_evidence(evidence_id))
    if not access.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "source_quote_not_authorized",
                "message": "This source is not authorized for public quotation",
            },
        )
    return evidence_detail_from_record(record)
