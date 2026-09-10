from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture.models import CopyrightStatus, SourceDocument, SourceFile, SourceLevel, SourceType
from wu_culture.repositories import InMemorySourceDocumentRepository, InMemorySourceFileRepository
from wu_culture.storage import ObjectKind, StoredObject

from app.gateway.auth.models import User
from app.gateway.routers import source_documents
from deerflow.config.corpus_import_config import CorpusImportConfig, CorpusRootConfig

ADMIN_ID = UUID("11111111-2222-3333-4444-555555555555")


class _MetadataRepository:
    def __init__(self, metadata: StoredObject) -> None:
        self.metadata = metadata

    async def get(self, *, owner_id: str, object_key: str):
        if owner_id == self.metadata.owner_id and object_key == self.metadata.object_key:
            return self.metadata
        return None


def _admin_user() -> User:
    return User(id=ADMIN_ID, email="admin@example.com", password_hash="x", system_role="admin")


def test_admin_streams_allowlisted_mounted_pdf_with_range_support(tmp_path):
    corpus_root = tmp_path / "corpus"
    pdf = corpus_root / "苏州" / "府志" / "book.pdf"
    pdf.parent.mkdir(parents=True)
    content = b"%PDF-1.4\nmounted corpus fixture"
    pdf.write_bytes(content)
    documents = InMemorySourceDocumentRepository()
    files = InMemorySourceFileRepository()
    now = datetime.now(UTC)
    document = SourceDocument(
        id="doc-1",
        title="府志",
        source_type=SourceType.GAZETTEER,
        source_level=SourceLevel.B,
        copyright_status=CopyrightStatus.UNKNOWN,
        source_institution="测试馆",
        holder="测试馆",
    )
    metadata = StoredObject(
        object_key="users/doc-1/mounted/fuxianzhi/苏州/府志/book.pdf",
        owner_id="doc-1",
        kind=ObjectKind.ORIGINAL,
        sha256="a" * 64,
        mime_type="application/pdf",
        size=len(content),
        backend="mounted",
        storage_uri="corpus://fuxianzhi/苏州/府志/book.pdf",
        original_filename="book.pdf",
        created_at=now,
    )
    source_file = SourceFile(
        id="file-1",
        document_id="doc-1",
        object_key=metadata.object_key,
        original_filename="book.pdf",
        mime_type="application/pdf",
        size=len(content),
        sha256=metadata.sha256,
        uploaded_by="admin-1",
        uploaded_at=now,
    )

    async def seed():
        await documents.create(document)
        await files.attach(source_file, metadata)

    import asyncio

    asyncio.run(seed())
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: files
    app.dependency_overrides[source_documents.get_ocr_object_metadata_repository] = lambda: _MetadataRepository(metadata)
    app.dependency_overrides[source_documents.get_corpus_import_config] = lambda: CorpusImportConfig(roots=(CorpusRootConfig(id="fuxianzhi", path=corpus_root),))
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        response = client.get("/api/source-documents/doc-1/files/file-1/content")
        partial = client.get(
            "/api/source-documents/doc-1/files/file-1/content",
            headers={"Range": "bytes=0-3"},
        )

    assert response.status_code == 200
    assert response.content == content
    assert partial.status_code == 206
    assert partial.content == content[:4]
