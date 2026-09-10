from __future__ import annotations

from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture.repositories import (
    InMemoryParsedDocumentRepository,
    InMemorySourceDocumentRepository,
    InMemorySourceFileRepository,
)

from app.gateway.auth.models import User
from app.gateway.routers import source_documents
from deerflow.object_storage import LocalObjectStorage

ADMIN_ID = UUID("11111111-2222-3333-4444-555555555555")


def _admin_user() -> User:
    return User(
        id=ADMIN_ID,
        email="admin@example.com",
        password_hash="x",
        system_role="admin",
    )


def test_admin_parses_uploaded_text_file_and_reads_persisted_result(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    parsed_documents = InMemoryParsedDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_parsed_document_repository] = lambda: parsed_documents
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        created = client.post(
            "/api/source-documents",
            json={
                "title": "木渎小志文本稿",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "gazetteer",
                "source_level": "A",
                "holder": "测试资料组",
            },
        ).json()
        upload = client.post(
            f"/api/source-documents/{created['id']}/files",
            files={"files": ("mudu.txt", "第一段。\n\n第二段。".encode(), "text/plain")},
        )
        uploaded_file = upload.json()["items"][0]["file"]
        parsed = client.post(f"/api/source-documents/{created['id']}/files/{uploaded_file['id']}/parse")
        restored = client.get(f"/api/source-documents/{created['id']}/files/{uploaded_file['id']}/parse")

    assert parsed.status_code == 200
    assert parsed.json()["reused_existing"] is False
    assert [block["text"] for block in parsed.json()["document"]["blocks"]] == ["第一段。", "第二段。"]
    assert restored.status_code == 200
    assert restored.json() == parsed.json()["document"]


def test_duplicate_source_reference_reuses_canonical_parse(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    parsed_documents = InMemoryParsedDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_parsed_document_repository] = lambda: parsed_documents
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        source_ids = []
        for title in ("来源一", "来源二"):
            source_ids.append(
                client.post(
                    "/api/source-documents",
                    json={
                        "title": title,
                        "edition": "测试版",
                        "source_institution": "测试机构",
                        "source_type": "archive",
                        "source_level": "B",
                        "holder": "测试资料组",
                    },
                ).json()["id"]
            )
        content = "相同原件正文。".encode()
        canonical_upload = client.post(
            f"/api/source-documents/{source_ids[0]}/files",
            files={"files": ("canonical.txt", content, "text/plain")},
        ).json()["items"][0]["file"]
        reference_upload = client.post(
            f"/api/source-documents/{source_ids[1]}/files",
            data={"duplicate_policy": "reference_existing"},
            files={"files": ("renamed.txt", content, "text/plain")},
        ).json()["items"][0]["file"]

        canonical_parse = client.post(f"/api/source-documents/{source_ids[0]}/files/{canonical_upload['id']}/parse")
        reference_parse = client.post(f"/api/source-documents/{source_ids[1]}/files/{reference_upload['id']}/parse")

    assert canonical_parse.json()["reused_existing"] is False
    assert reference_parse.json()["reused_existing"] is True
    assert reference_parse.json()["document"] == canonical_parse.json()["document"]
    assert reference_parse.json()["document"]["source_file_id"] == canonical_upload["id"]


def test_parse_endpoint_returns_structured_reason_for_damaged_pdf(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    parsed_documents = InMemoryParsedDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_parsed_document_repository] = lambda: parsed_documents
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        source_id = client.post(
            "/api/source-documents",
            json={
                "title": "损坏 PDF",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()["id"]
        uploaded = client.post(
            f"/api/source-documents/{source_id}/files",
            files={"files": ("broken.pdf", b"%PDF-1.7\nbroken", "application/pdf")},
        ).json()["items"][0]["file"]
        response = client.post(f"/api/source-documents/{source_id}/files/{uploaded['id']}/parse")

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "invalid_pdf", "message": "PDF is damaged or invalid"}
