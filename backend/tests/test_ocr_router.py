from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture.ocr import OcrBoundingBox, OcrPageAttempt, OcrPageStatus, OcrProviderPage, OcrRegion, OcrService
from wu_culture.repositories import InMemorySourceDocumentRepository, InMemorySourceFileRepository

from app.gateway.auth.models import User
from app.gateway.routers import source_documents
from deerflow.config.ocr_config import OcrConfig
from deerflow.object_storage import LocalObjectStorage


def _admin_user() -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email="admin@example.com",
        password_hash="x",
        system_role="admin",
    )


def _blank_pdf(page_count: int) -> bytes:
    page_ids = [3 + index for index in range(page_count)]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {page_count} >>".encode(),
        *(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 144] >>" for _ in page_ids),
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode())
        result.extend(body)
        result.extend(b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(result)


class _PartialProvider:
    name = "test-ocr"
    model = "vision-model"

    def __init__(self):
        self.calls = {}

    async def recognize(self, page, *, languages):
        self.calls[page.page_number] = self.calls.get(page.page_number, 0) + 1
        if page.page_number == 2 and self.calls[page.page_number] == 1:
            raise RuntimeError("page failed")
        return OcrProviderPage(
            raw_text="木渎",
            mean_confidence=0.95,
            rotation_degrees=0,
            regions=(OcrRegion(text="木渎", confidence=0.95, bounding_box=OcrBoundingBox(x=0.1, y=0.2, width=0.3, height=0.1)),),
        )


class _InMemoryOcrRepository:
    def __init__(self):
        self.attempts = []

    async def save_attempts(self, attempts):
        self.attempts.extend(attempts)

    async def list_latest(self, source_file_id):
        latest = {}
        for attempt in self.attempts:
            if attempt.source_file_id == source_file_id:
                latest[attempt.page_number] = attempt
        return [latest[page_number] for page_number in sorted(latest)]

    async def list_review_queue(self):
        latest = {}
        for attempt in self.attempts:
            latest[(attempt.source_file_id, attempt.page_number)] = attempt
        return [attempt for attempt in latest.values() if attempt.status is OcrPageStatus.REVIEW_REQUIRED]


class _InMemoryObjectMetadataRepository:
    async def save(self, metadata):
        return None


def test_admin_ocr_batch_preserves_successful_page_when_sibling_page_fails(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    ocr_repository = _InMemoryOcrRepository()
    provider = _PartialProvider()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_ocr_repository] = lambda: ocr_repository
    app.dependency_overrides[source_documents.get_ocr_object_metadata_repository] = lambda: _InMemoryObjectMetadataRepository()
    app.dependency_overrides[source_documents.get_ocr_service] = lambda: OcrService(
        provider,
        languages=("zh-Hans",),
        review_confidence_threshold=0.8,
        max_concurrency=2,
    )
    app.dependency_overrides[source_documents.get_ocr_config] = lambda: OcrConfig(enabled=True, model_name="vision-model")
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        document = client.post(
            "/api/source-documents",
            json={
                "title": "扫描资料",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()
        uploaded = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("scan.pdf", _blank_pdf(2), "application/pdf")},
        ).json()["items"][0]["file"]
        response = client.post(f"/api/source-documents/{document['id']}/files/{uploaded['id']}/ocr")
        restored = client.get(f"/api/source-documents/{document['id']}/files/{uploaded['id']}/ocr")
        retried = client.post(f"/api/source-documents/{document['id']}/files/{uploaded['id']}/ocr/pages/2/retry")
        rejected_retry = client.post(f"/api/source-documents/{document['id']}/files/{uploaded['id']}/ocr/pages/1/retry")
        after_retry = client.get(f"/api/source-documents/{document['id']}/files/{uploaded['id']}/ocr")

    assert response.status_code == 200
    assert response.json()["source_file_id"] == uploaded["id"]
    assert [item["status"] for item in response.json()["attempts"]] == [OcrPageStatus.COMPLETED, OcrPageStatus.FAILED]
    assert restored.json()["attempts"] == response.json()["attempts"]
    assert retried.status_code == 200
    assert retried.json()["page_number"] == 2
    assert retried.json()["attempt_number"] == 2
    assert retried.json()["status"] == OcrPageStatus.COMPLETED
    assert [item["attempt_number"] for item in after_retry.json()["attempts"]] == [1, 2]
    assert provider.calls == {1: 1, 2: 2}
    assert rejected_retry.status_code == 409
    assert rejected_retry.json()["detail"]["code"] == "ocr_page_not_failed"


def test_admin_lists_latest_low_confidence_pages_for_review():
    repository = _InMemoryOcrRepository()
    repository.attempts.append(
        OcrPageAttempt(
            id="ocr-file-review-p3-a1",
            source_file_id="file-review",
            page_number=3,
            attempt_number=1,
            image_sha256="a" * 64,
            image_width=100,
            image_height=200,
            provider_name="test-ocr",
            model_name="vision-model",
            languages=("zh-Hans",),
            status=OcrPageStatus.REVIEW_REQUIRED,
            raw_text="待校对",
            mean_confidence=0.65,
            regions=(OcrRegion(text="待校对", confidence=0.65, bounding_box=OcrBoundingBox(x=0.1, y=0.2, width=0.3, height=0.1)),),
            created_at=datetime.now(UTC),
        )
    )
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_ocr_repository] = lambda: repository
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        response = client.get("/api/source-documents/ocr/review-queue")

    assert response.status_code == 200
    assert [(item["source_file_id"], item["page_number"], item["status"]) for item in response.json()] == [("file-review", 3, OcrPageStatus.REVIEW_REQUIRED)]


def test_duplicate_source_reference_reuses_canonical_ocr(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    ocr_repository = _InMemoryOcrRepository()
    provider = _PartialProvider()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_ocr_repository] = lambda: ocr_repository
    app.dependency_overrides[source_documents.get_ocr_object_metadata_repository] = lambda: _InMemoryObjectMetadataRepository()
    app.dependency_overrides[source_documents.get_ocr_service] = lambda: OcrService(
        provider,
        languages=("zh-Hans",),
        review_confidence_threshold=0.8,
        max_concurrency=1,
    )
    app.dependency_overrides[source_documents.get_ocr_config] = lambda: OcrConfig(enabled=True, model_name="vision-model")
    app.include_router(source_documents.router)

    source_body = {
        "title": "扫描资料",
        "edition": "测试版",
        "source_institution": "测试机构",
        "source_type": "archive",
        "source_level": "B",
        "holder": "测试资料组",
    }
    content = _blank_pdf(1)
    with TestClient(app) as client:
        first_source = client.post("/api/source-documents", json=source_body).json()
        second_source = client.post("/api/source-documents", json={**source_body, "edition": "引用版"}).json()
        canonical = client.post(
            f"/api/source-documents/{first_source['id']}/files",
            files={"files": ("scan.pdf", content, "application/pdf")},
        ).json()["items"][0]["file"]
        reference = client.post(
            f"/api/source-documents/{second_source['id']}/files",
            data={"duplicate_policy": "reference_existing"},
            files={"files": ("scan-copy.pdf", content, "application/pdf")},
        ).json()["items"][0]["file"]

        first_ocr = client.post(f"/api/source-documents/{first_source['id']}/files/{canonical['id']}/ocr")
        reused_ocr = client.post(f"/api/source-documents/{second_source['id']}/files/{reference['id']}/ocr")

    assert first_ocr.json()["reused_existing"] is False
    assert reused_ocr.json()["reused_existing"] is True
    assert reused_ocr.json()["source_file_id"] == canonical["id"]
    assert reused_ocr.json()["attempts"] == first_ocr.json()["attempts"]
    assert provider.calls == {1: 1}
