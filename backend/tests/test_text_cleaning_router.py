from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from PIL import Image
from wu_culture.ocr import OcrPageAttempt, OcrPageStatus
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


class _InMemoryOcrRepository:
    def __init__(self):
        self.attempts = []

    async def list_latest(self, source_file_id):
        return [attempt for attempt in self.attempts if attempt.source_file_id == source_file_id]


class _InMemoryTextCleaningRepository:
    def __init__(self):
        self.pages = []

    async def save_many(self, pages):
        self.pages.extend(pages)

    async def list_latest(self, source_file_id):
        latest = {}
        for page in self.pages:
            if page.source_file_id == source_file_id:
                latest[page.page_number] = page
        return [latest[number] for number in sorted(latest)]

    async def list_page_generations(self, source_file_id, page_number):
        return [page for page in self.pages if page.source_file_id == source_file_id and page.page_number == page_number]


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 10), "white").save(output, format="PNG")
    return output.getvalue()


def test_admin_regenerates_clean_text_without_changing_raw_ocr(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    ocr_repository = _InMemoryOcrRepository()
    cleaning_repository = _InMemoryTextCleaningRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_ocr_repository] = lambda: ocr_repository
    app.dependency_overrides[source_documents.get_text_cleaning_repository] = lambda: cleaning_repository
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        document = client.post(
            "/api/source-documents",
            json={
                "title": "清洗测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()
        source_file = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("scan.png", _png_bytes(), "image/png")},
        ).json()["items"][0]["file"]
        ocr_repository.attempts.append(
            OcrPageAttempt(
                id=f"ocr-{source_file['id']}-p1-a1",
                source_file_id=source_file["id"],
                page_number=1,
                attempt_number=1,
                image_sha256="a" * 64,
                image_width=20,
                image_height=10,
                provider_name="test-ocr",
                model_name="vision-model",
                languages=("zh-Hant",),
                status=OcrPageStatus.COMPLETED,
                raw_text="後臺\n史料",
                mean_confidence=0.95,
                created_at=datetime.now(UTC),
            )
        )

        first = client.post(
            f"/api/source-documents/{document['id']}/files/{source_file['id']}/clean",
            json={"rule_version": "clean-v1", "script_conversion": "simplified"},
        )
        second = client.post(
            f"/api/source-documents/{document['id']}/files/{source_file['id']}/clean",
            json={"rule_version": "clean-v2", "script_conversion": "preserve"},
        )
        latest = client.get(f"/api/source-documents/{document['id']}/files/{source_file['id']}/clean")
        history = client.get(f"/api/source-documents/{document['id']}/files/{source_file['id']}/clean/pages/1/generations")

    assert first.status_code == 200
    assert first.json()["pages"][0]["generation_number"] == 1
    assert first.json()["pages"][0]["raw_text"] == "後臺\n史料"
    assert first.json()["pages"][0]["clean_text"] == "后台史料"
    assert second.json()["pages"][0]["generation_number"] == 2
    assert second.json()["pages"][0]["raw_sha256"] == first.json()["pages"][0]["raw_sha256"]
    assert latest.json()["pages"] == second.json()["pages"]
    assert [item["generation_number"] for item in history.json()] == [1, 2]
