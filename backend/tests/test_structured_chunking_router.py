from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from PIL import Image
from wu_culture.cleaning import CleanedOcrPage, RawOcrPage, TextCleaningPolicy, clean_ocr_page
from wu_culture.repositories import InMemorySourceDocumentRepository, InMemorySourceFileRepository

from app.gateway.auth.models import User
from app.gateway.routers import source_documents
from deerflow.object_storage import LocalObjectStorage


def _admin_user() -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email="admin@example.com",
        password_hash="x",
        system_role="admin",
    )


class _InMemoryCleaningRepository:
    def __init__(self, pages):
        self.pages = pages

    async def list_latest(self, source_file_id):
        return [page for page in self.pages if page.source_file_id == source_file_id]


class _InMemoryChunkRepository:
    def __init__(self):
        self.sets = []

    async def save(self, chunk_set):
        self.sets.append(chunk_set)

    async def get(self, source_file_id, split_version):
        return next((item for item in self.sets if item.source_file_id == source_file_id and item.policy.split_version == split_version), None)

    async def list_versions(self, source_file_id):
        return [item for item in self.sets if item.source_file_id == source_file_id]


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 10), "white").save(output, format="PNG")
    return output.getvalue()


def test_admin_creates_reuses_and_versions_structured_chunks(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    chunk_repository = _InMemoryChunkRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_structured_chunk_repository] = lambda: chunk_repository
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        document = client.post(
            "/api/source-documents",
            json={
                "title": "切分测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "gazetteer",
                "source_level": "A",
                "holder": "测试资料组",
            },
        ).json()
        source_file = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("scan.png", _png_bytes(), "image/png")},
        ).json()["items"][0]["file"]
        raw_page = RawOcrPage(
            source_file_id=source_file["id"],
            ocr_attempt_id=f"ocr-{source_file['id']}-p1-a1",
            page_number=1,
            raw_text="卷一\n目一\n木渎沿河。",
        )
        cleaning_policy = TextCleaningPolicy(rule_version="clean-v1")
        cleaned_content = clean_ocr_page(raw_page, policy=cleaning_policy)
        cleaned_page = CleanedOcrPage(
            id="cleaned-page-1-g1",
            generation_number=1,
            policy=cleaning_policy,
            generated_by="admin-1",
            generated_at=datetime.now(UTC),
            **cleaned_content.model_dump(),
        )
        cleaning_repository = _InMemoryCleaningRepository([cleaned_page])
        app.dependency_overrides[source_documents.get_text_cleaning_repository] = lambda: cleaning_repository

        body = {"split_version": "structure-v1", "max_characters": 200, "overlap_characters": 20}
        created = client.post(f"/api/source-documents/{document['id']}/files/{source_file['id']}/chunks", json=body)
        reused = client.post(f"/api/source-documents/{document['id']}/files/{source_file['id']}/chunks", json=body)
        conflict = client.post(
            f"/api/source-documents/{document['id']}/files/{source_file['id']}/chunks",
            json={**body, "max_characters": 100},
        )
        rebuilt = client.post(
            f"/api/source-documents/{document['id']}/files/{source_file['id']}/chunks",
            json={**body, "split_version": "structure-v2", "max_characters": 100},
        )
        versions = client.get(f"/api/source-documents/{document['id']}/files/{source_file['id']}/chunks")

    assert created.status_code == 200
    assert created.json()["reused_existing"] is False
    assert created.json()["chunk_set"]["chunks"][0]["clean_text"] == "木渎沿河。"
    assert reused.json()["reused_existing"] is True
    assert reused.json()["chunk_set"] == created.json()["chunk_set"]
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "split_version_conflict"
    assert rebuilt.status_code == 200
    assert rebuilt.json()["chunk_set"]["chunks"][0]["id"] != created.json()["chunk_set"]["chunks"][0]["id"]
    assert [item["policy"]["split_version"] for item in versions.json()] == ["structure-v1", "structure-v2"]
