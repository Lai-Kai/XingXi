from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture import AuthorizedUse, SearchStatus
from wu_culture.filters import StructuredSearchFilters
from wu_culture.hybrid import (
    HybridChannel,
    HybridChannelReport,
    HybridChannelStatus,
    HybridSearchResponse,
)
from wu_culture.structured_search import StructuredSearchResponse
from wu_culture.vectors import (
    VectorIndexState,
    VectorIndexStatus,
    VectorIndexVersion,
    VectorSearchResponse,
)

from app.gateway.auth.models import User
from app.gateway.auth_disabled import AUTH_SOURCE_SESSION
from app.gateway.routers import knowledge_search

NOW = datetime(2026, 7, 21, 22, 30, tzinfo=UTC)


def _user(role: str = "admin") -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email=f"{role}@example.com",
        password_hash="x",
        system_role=role,
    )


class _Service:
    def __init__(self) -> None:
        self.request = None

    async def search(self, request):
        self.request = request
        return VectorSearchResponse(
            query=request.query,
            release_id="release-1",
            index_id="vector-1",
            embedding_model="test-embedding",
            embedding_version="v1",
            hits=(),
        )

    async def rebuild(self, release_id, *, expected_state_version, actor_id, started_at):
        return VectorIndexVersion(
            id="vector-1",
            release_id=release_id,
            release_manifest_sha256="a" * 64,
            embedding_model="test-embedding",
            embedding_version="v1",
            dimensions=2,
            status=VectorIndexStatus.READY,
            item_count=2,
            created_by=actor_id,
            created_at=started_at,
            completed_at=NOW,
        )


class _Repository:
    async def get_state(self, release_id):
        return VectorIndexState(release_id=release_id, active_index_id="vector-1", state_version=1, updated_at=NOW)

    async def list_versions(self, release_id):
        return []


class _HybridService:
    def __init__(self) -> None:
        self.request = None

    async def search(self, request):
        self.request = request
        return HybridSearchResponse(
            query=request.query,
            release_id="release-1",
            rrf_k=60,
            degraded=True,
            channel_reports=(
                HybridChannelReport(channel=HybridChannel.FULLTEXT, status=HybridChannelStatus.EMPTY),
                HybridChannelReport(channel=HybridChannel.VECTOR, status=HybridChannelStatus.UNAVAILABLE),
            ),
            hits=(),
            evidence_status=SearchStatus.INSUFFICIENT,
            message="暂无明确方志记载",
        )


class _StructuredService:
    def __init__(self) -> None:
        self.request = None

    async def search(self, request):
        self.request = request
        return StructuredSearchResponse(
            query=request.query,
            release_id="release-1",
            filters=request.filters,
            page_size=request.page_size,
            returned_count=0,
            candidate_count=0,
            has_more=False,
            degraded=False,
            channel_reports=(
                HybridChannelReport(channel=HybridChannel.FULLTEXT, status=HybridChannelStatus.EMPTY),
                HybridChannelReport(channel=HybridChannel.VECTOR, status=HybridChannelStatus.EMPTY),
            ),
            evidence_status=SearchStatus.INSUFFICIENT,
            message="暂无明确方志记载",
            hits=(),
        )


def _app(role="admin"):
    app = make_authed_test_app(user_factory=lambda: _user(role))

    @app.middleware("http")
    async def stamp_auth_source(request, call_next):
        request.state.auth_source = AUTH_SOURCE_SESSION
        return await call_next(request)

    app.include_router(knowledge_search.router)
    return app


def test_vector_search_forces_public_quote_scope() -> None:
    service = _Service()
    app = _app()
    app.dependency_overrides[knowledge_search.get_vector_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge-search/vector",
            json={"query": "旧桥", "authorized_use": "internal_processing"},
        )

    assert response.status_code == 200
    assert service.request.authorized_use is AuthorizedUse.PUBLIC_QUOTE


def test_non_admin_cannot_rebuild_or_inspect_vector_indexes() -> None:
    app = _app("user")
    app.dependency_overrides[knowledge_search.get_vector_service] = _Service
    app.dependency_overrides[knowledge_search.get_vector_repository] = _Repository

    with TestClient(app) as client:
        rebuild = client.post(
            "/api/knowledge-search/vector/rebuild",
            json={"release_id": "release-1", "expected_state_version": 0},
        )
        state = client.get("/api/knowledge-search/vector/releases/release-1/state")

    assert rebuild.status_code == 403
    assert state.status_code == 403


def test_hybrid_search_forces_public_quote_and_returns_degraded_state() -> None:
    service = _HybridService()
    app = _app()
    app.dependency_overrides[knowledge_search.get_hybrid_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge-search/hybrid",
            json={"query": "旧桥", "authorized_use": "internal_processing"},
        )

    assert response.status_code == 200
    assert response.json()["degraded"] is True
    assert service.request.authorized_use is AuthorizedUse.PUBLIC_QUOTE


def test_structured_search_uses_shared_typed_filter_schema() -> None:
    service = _StructuredService()
    app = _app()
    app.dependency_overrides[knowledge_search.get_structured_search_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge-search/structured",
            json={
                "query": "旧桥",
                "filters": {
                    "editions": ["测试版"],
                    "dynasties": ["qing"],
                    "entity_types": ["bridge"],
                    "min_spatial_confidence": 0.8,
                },
            },
        )
        invalid = client.post(
            "/api/knowledge-search/structured",
            json={"query": "旧桥", "filters": {"dynasties": ["not-a-dynasty"]}},
        )
        undeclared = client.post(
            "/api/knowledge-search/structured",
            json={"query": "旧桥", "filters": {"sql": "1=1"}},
        )
        schema = client.get("/api/knowledge-search/structured/filters/schema")

    assert response.status_code == 200
    assert service.request.filters == StructuredSearchFilters(
        editions=("测试版",),
        dynasties=("qing",),
        entity_types=("bridge",),
        min_spatial_confidence=0.8,
    )
    assert invalid.status_code == 422
    assert undeclared.status_code == 422
    assert schema.status_code == 200
    assert set(schema.json()["properties"]) == {
        "document_ids",
        "editions",
        "source_types",
        "source_levels",
        "dynasties",
        "entity_types",
        "review_statuses",
        "min_spatial_confidence",
        "max_spatial_confidence",
    }
