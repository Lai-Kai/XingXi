from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture import (
    CopyrightStatus,
    SourceDocument,
    SourceDocumentLibraryFile,
    SourceDocumentLibraryItem,
    SourceDocumentStatus,
    SourceFile,
    SourceLevel,
    SourceType,
)
from wu_culture.ingestion import create_ingestion_job

from app.gateway.auth.models import User
from app.gateway.routers import source_documents

ADMIN_ID = UUID("11111111-2222-3333-4444-555555555555")


def _admin_user() -> User:
    return User(
        id=ADMIN_ID,
        email="admin@example.com",
        password_hash="x",
        system_role="admin",
    )


def _source() -> SourceDocument:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return SourceDocument(
        id="source-1",
        title="木渎小志",
        edition="民国十二年刻本",
        source_institution="苏州地方文献馆",
        source_type=SourceType.GAZETTEER,
        source_level=SourceLevel.A,
        holder="星羲项目资料组",
        copyright_status=CopyrightStatus.UNKNOWN,
        status=SourceDocumentStatus.REGISTERED,
        created_by=str(ADMIN_ID),
        created_at=now,
        updated_by=str(ADMIN_ID),
        updated_at=now,
    )


def _library_item() -> SourceDocumentLibraryItem:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    job, _ = create_ingestion_job(
        job_id="job-1",
        document_id="source-1",
        source_file_id="file-1",
        idempotency_key="source-file:file-1",
        created_by=str(ADMIN_ID),
        now=now,
    )
    source_file = SourceFile(
        id="file-1",
        document_id="source-1",
        object_key="users/source-1/objects/original/ab/" + "a" * 64,
        original_filename="mudu.pdf",
        mime_type="application/pdf",
        size=128,
        sha256="a" * 64,
        uploaded_by=str(ADMIN_ID),
        uploaded_at=now,
    )
    return SourceDocumentLibraryItem(
        document=_source(),
        files=(SourceDocumentLibraryFile(file=source_file, ingestion_job=job),),
    )


class _LibraryRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def list_library_page(self, **kwargs):
        self.calls.append(kwargs)
        return [_library_item()], 1


def test_library_page_returns_sources_files_and_latest_ingestion_job() -> None:
    repository = _LibraryRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_library_repository] = lambda: repository
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        response = client.get(
            "/api/source-documents/library/page?query=木渎&status_filter=registered&limit=10&offset=20"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 20
    assert payload["items"][0]["source"]["id"] == "source-1"
    assert payload["items"][0]["files"][0]["file"]["id"] == "file-1"
    assert payload["items"][0]["files"][0]["ingestion_job"]["id"] == "job-1"
    assert repository.calls == [{"query": "木渎", "status": "registered", "limit": 10, "offset": 20}]
