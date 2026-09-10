from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from wu_culture import (
    AuthorizationStatus,
    AuthorizedUse,
    CopyrightStatus,
    Evidence,
    EvidenceRecord,
    ReviewStatus,
    SourceDocument,
    SourceDocumentStatus,
    SourceLevel,
    SourceType,
    TextChunk,
    VisibilityScope,
)

from app.gateway.routers import public_knowledge


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(public_knowledge.router)
    return app


def _record(*, uses: tuple[AuthorizedUse, ...]) -> EvidenceRecord:
    document = SourceDocument(
        id="doc-1",
        title="Public source",
        edition="First",
        source_type=SourceType.GAZETTEER,
        source_level=SourceLevel.A,
        copyright_status=CopyrightStatus.AUTHORIZED,
        authorization_status=AuthorizationStatus.ACTIVE,
        authorization_basis="Written permission",
        visibility_scope=VisibilityScope.PUBLIC,
        authorized_uses=uses,
        status=SourceDocumentStatus.REGISTERED,
    )
    chunk = TextChunk(
        id="chunk-1",
        document_id=document.id,
        original_text="Original text",
        normalized_text="Original text",
        page_start=1,
        page_end=1,
        review_status=ReviewStatus.REVIEWED,
    )
    return EvidenceRecord(
        document=document,
        chunk=chunk,
        evidence=Evidence(
            id="evidence-1",
            document_id=document.id,
            chunk_id=chunk.id,
            quote="Quoted text",
            source_level=SourceLevel.A,
            review_status=ReviewStatus.REVIEWED,
        ),
    )


def test_public_health_is_registered_and_read_only() -> None:
    with TestClient(_app()) as client:
        response = client.get("/api/public/knowledge/health")
        paths = {route.path for route in client.app.routes}

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "surface": "public-knowledge", "mode": "controlled"}
    assert "/api/public/knowledge/evidence/{evidence_id}" in paths
    assert "/api/public/knowledge/search" not in paths
    assert "/api/public/knowledge/release" not in paths


def test_missing_sql_database_returns_service_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(public_knowledge, "get_session_factory", lambda: None)
    with TestClient(_app()) as client:
        response = client.get("/api/public/knowledge/evidence/missing")
    assert response.status_code == 503


def test_missing_evidence_returns_not_found(monkeypatch) -> None:
    class EmptyRepository:
        def __init__(self, session_factory):
            pass

        async def get_evidence(self, evidence_id):
            return None

    import deerflow.persistence.wu_culture as persistence_wu_culture

    monkeypatch.setattr(public_knowledge, "get_session_factory", lambda: object())
    monkeypatch.setattr(persistence_wu_culture, "SqlEvidenceRepository", EmptyRepository)
    with TestClient(_app()) as client:
        response = client.get("/api/public/knowledge/evidence/missing")
    assert response.status_code == 404


def test_public_use_is_enforced_for_authorized_source(monkeypatch) -> None:
    record = _record(uses=(AuthorizedUse.PUBLIC_QUOTE,))

    class Repository:
        def __init__(self, session_factory):
            pass

        async def get_evidence(self, evidence_id):
            return record

    import deerflow.persistence.wu_culture as persistence_wu_culture

    monkeypatch.setattr(public_knowledge, "get_session_factory", lambda: object())
    monkeypatch.setattr(persistence_wu_culture, "SqlEvidenceRepository", Repository)
    with TestClient(_app()) as client:
        allowed = client.get("/api/public/knowledge/evidence/evidence-1", params={"use": "public_quote"})
        denied = client.get("/api/public/knowledge/evidence/evidence-1", params={"use": "public_full_text"})
        unsafe = client.get("/api/public/knowledge/evidence/evidence-1", params={"use": "internal_processing"})

    assert allowed.status_code == 200
    assert allowed.json()["href"] == "evidence://evidence-1"
    assert denied.status_code == 403
    assert unsafe.status_code == 403
