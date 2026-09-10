from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from wu_culture import (
    AuthorizationStatus,
    AuthorizedUse,
    CopyrightStatus,
    SourceDocument,
    SourceLevel,
    SourceType,
    VisibilityScope,
)
from wu_culture.repositories import InMemorySourceDocumentRepository

from app.gateway.auth.models import User
from app.gateway.auth_middleware import AuthMiddleware
from app.gateway.routers import source_documents

ADMIN_ID = UUID("11111111-2222-3333-4444-555555555555")


def _admin_user() -> User:
    return User(
        id=ADMIN_ID,
        email="admin@example.com",
        password_hash="x",
        system_role="admin",
    )


def _regular_user() -> User:
    return User(
        id=UUID("99999999-8888-7777-6666-555555555555"),
        email="user@example.com",
        password_hash="x",
        system_role="user",
    )


def test_admin_can_authorize_public_full_text_and_access_check_allows_it():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)
    app.include_router(source_documents.public_router)
    valid_until = datetime.now(UTC) + timedelta(days=30)

    with TestClient(app) as client:
        created = client.post(
            "/api/source-documents",
            json={
                "title": "Authorized source",
                "edition": "First edition",
                "source_institution": "Archive",
                "source_type": "archive",
                "source_level": "A",
                "holder": "Rights holder",
            },
        ).json()
        authorization = client.put(
            f"/api/source-documents/{created['id']}/authorization",
            json={
                "copyright_status": "authorized",
                "authorization_status": "active",
                "authorization_basis": "Written permission dated 2026-07-01",
                "authorization_valid_until": valid_until.isoformat(),
                "visibility_scope": "public",
                "authorized_uses": ["public_full_text", "public_quote"],
                "authorization_proof_object_key": "users/admin/objects/original/aa/proof",
                "change_reason": "Initial rights review",
            },
        )
        access = client.get(
            f"/api/public/source-documents/{created['id']}/access",
            params={"use": "public_full_text"},
        )

    assert authorization.status_code == 200
    assert authorization.json()["authorization_status"] == "active"
    assert authorization.json()["authorization_basis"] == "Written permission dated 2026-07-01"
    assert authorization.json()["visibility_scope"] == "public"
    assert authorization.json()["authorized_uses"] == ["public_full_text", "public_quote"]
    assert access.status_code == 200
    assert access.json() == {
        "use": "public_full_text",
        "allowed": True,
        "reason": "authorized",
        "effective_status": "active",
    }


def test_authorization_changes_append_audit_history():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)
    app.include_router(source_documents.public_router)

    with TestClient(app) as client:
        created = client.post(
            "/api/source-documents",
            json={
                "title": "Audited source",
                "edition": "First edition",
                "source_institution": "Archive",
                "source_type": "archive",
                "source_level": "B",
                "holder": "Rights holder",
            },
        ).json()
        client.put(
            f"/api/source-documents/{created['id']}/authorization",
            json={
                "copyright_status": "authorized",
                "authorization_status": "active",
                "authorization_basis": "Written permission",
                "visibility_scope": "public",
                "authorized_uses": ["public_quote"],
                "change_reason": "Initial review",
            },
        )
        client.put(
            f"/api/source-documents/{created['id']}/authorization",
            json={
                "copyright_status": "restricted",
                "authorization_status": "revoked",
                "authorization_basis": "Rights holder withdrew permission",
                "visibility_scope": "internal",
                "authorized_uses": [],
                "change_reason": "Permission withdrawn",
            },
        )
        history = client.get(f"/api/source-documents/{created['id']}/authorization/history")

    assert history.status_code == 200
    events = history.json()
    assert len(events) == 2
    assert events[0]["previous_status"] == "unconfirmed"
    assert events[0]["new_status"] == "active"
    assert events[0]["reason"] == "Initial review"
    assert events[1]["previous_status"] == "active"
    assert events[1]["new_status"] == "revoked"
    assert events[1]["reason"] == "Permission withdrawn"
    assert all(event["changed_by"] == str(ADMIN_ID) for event in events)


def test_public_access_decision_does_not_require_login():
    repository = InMemorySourceDocumentRepository()
    asyncio.run(
        repository.create(
            SourceDocument(
                id="source-public",
                title="Public source",
                source_type=SourceType.ARCHIVE,
                source_level=SourceLevel.A,
                copyright_status=CopyrightStatus.AUTHORIZED,
                authorization_status=AuthorizationStatus.ACTIVE,
                authorization_basis="Written permission",
                visibility_scope=VisibilityScope.PUBLIC,
                authorized_uses=(AuthorizedUse.PUBLIC_QUOTE,),
            )
        )
    )
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.public_router)

    with TestClient(app) as client:
        response = client.get(
            "/api/public/source-documents/source-public/access",
            params={"use": "public_quote"},
        )

    assert response.status_code == 200
    assert response.json()["allowed"] is True


def test_authorization_update_rejects_unsafe_or_incomplete_policy():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        created = client.post(
            "/api/source-documents",
            json={
                "title": "Validation source",
                "edition": "First edition",
                "source_institution": "Archive",
                "source_type": "archive",
                "source_level": "B",
                "holder": "Rights holder",
            },
        ).json()
        path = f"/api/source-documents/{created['id']}/authorization"
        missing_basis = client.put(
            path,
            json={
                "copyright_status": "authorized",
                "authorization_status": "active",
                "visibility_scope": "public",
                "authorized_uses": ["public_quote"],
                "change_reason": "Invalid active policy",
            },
        )
        reversed_dates = client.put(
            path,
            json={
                "copyright_status": "authorized",
                "authorization_status": "active",
                "authorization_basis": "Written permission",
                "authorization_valid_from": "2026-08-01T00:00:00Z",
                "authorization_valid_until": "2026-07-01T00:00:00Z",
                "visibility_scope": "public",
                "authorized_uses": ["public_quote"],
                "change_reason": "Invalid date range",
            },
        )
        unconfirmed_grant = client.put(
            path,
            json={
                "copyright_status": "unknown",
                "authorization_status": "unconfirmed",
                "visibility_scope": "public",
                "authorized_uses": ["public_full_text"],
                "change_reason": "Must default deny",
            },
        )

    assert [missing_basis.status_code, reversed_dates.status_code, unconfirmed_grant.status_code] == [422, 422, 422]


def test_authorization_mutation_and_history_require_admin():
    repository = InMemorySourceDocumentRepository()
    asyncio.run(
        repository.create(
            SourceDocument(
                id="source-admin-only",
                title="Admin-only source",
                source_type=SourceType.ARCHIVE,
                source_level=SourceLevel.B,
                copyright_status=CopyrightStatus.UNKNOWN,
            )
        )
    )
    app = make_authed_test_app(user_factory=_regular_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        update = client.put(
            "/api/source-documents/source-admin-only/authorization",
            json={
                "copyright_status": "authorized",
                "authorization_status": "active",
                "authorization_basis": "Written permission",
                "visibility_scope": "public",
                "authorized_uses": ["public_quote"],
                "change_reason": "Unauthorized attempt",
            },
        )
        history = client.get("/api/source-documents/source-admin-only/authorization/history")

    assert update.status_code == 403
    assert history.status_code == 403
