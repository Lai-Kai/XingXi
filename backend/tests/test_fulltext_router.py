from __future__ import annotations

import asyncio
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture import AuthorizedUse
from wu_culture.fulltext import FullTextIndexResult, FullTextSearchResponse

from app.gateway.auth.models import User
from app.gateway.auth_disabled import AUTH_SOURCE_SESSION
from app.gateway.routers import knowledge_search


def _user(role: str = "admin") -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email=f"{role}@example.com",
        password_hash="x",
        system_role=role,
    )


class _Repository:
    def __init__(self) -> None:
        self.request = None

    async def search(self, request):
        self.request = request
        return FullTextSearchResponse(
            query=request.query,
            release_id="release-1",
            release_version="v1",
            total=0,
            page=request.page,
            page_size=request.page_size,
            hits=(),
        )

    async def rebuild_release(self, release_id, *, indexed_at):
        return FullTextIndexResult(release_id=release_id, release_version="v1", indexed_chunks=3, indexed_at=indexed_at)


class _ScopeSession:
    def __init__(self, scope: str | None) -> None:
        self.scope = scope

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def scalar(self, _statement):
        return self.scope


class _ScopeSessionFactory:
    def __init__(self, scope: str | None) -> None:
        self.scope = scope

    def __call__(self):
        return _ScopeSession(self.scope)


def test_authenticated_search_forces_public_quote_scope() -> None:
    repository = _Repository()
    app = make_authed_test_app(user_factory=_user)

    @app.middleware("http")
    async def stamp_auth_source(request, call_next):
        request.state.auth_source = AUTH_SOURCE_SESSION
        return await call_next(request)

    app.dependency_overrides[knowledge_search.get_fulltext_repository] = lambda: repository
    app.include_router(knowledge_search.router)

    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge-search/fulltext",
            json={"query": "木渎", "authorized_use": "internal_processing"},
        )

    assert response.status_code == 200
    assert repository.request.authorized_use is AuthorizedUse.PUBLIC_QUOTE


def test_non_admin_cannot_rebuild_index() -> None:
    app = make_authed_test_app(user_factory=lambda: _user("user"))
    app.dependency_overrides[knowledge_search.get_fulltext_repository] = _Repository
    app.include_router(knowledge_search.router)

    with TestClient(app) as client:
        response = client.post("/api/knowledge-search/fulltext/releases/release-1/rebuild")

    assert response.status_code == 403


def test_authenticated_internal_release_evidence_uses_internal_processing(monkeypatch) -> None:
    monkeypatch.setattr(knowledge_search, "get_session_factory", lambda: _ScopeSessionFactory("internal"))

    use = asyncio.run(knowledge_search._authorized_use_for_evidence("evidence-internal"))

    assert use is AuthorizedUse.INTERNAL_PROCESSING


def test_public_or_unversioned_evidence_keeps_public_quote_scope(monkeypatch) -> None:
    for scope in ("public", None):
        monkeypatch.setattr(knowledge_search, "get_session_factory", lambda scope=scope: _ScopeSessionFactory(scope))
        assert asyncio.run(knowledge_search._authorized_use_for_evidence("evidence-public")) is AuthorizedUse.PUBLIC_QUOTE
