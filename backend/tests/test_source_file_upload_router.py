from __future__ import annotations

from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture.repositories import InMemorySourceDocumentRepository, InMemorySourceFileRepository

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


def test_admin_uploads_pdf_and_binds_it_to_registered_source(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        created = client.post(
            "/api/source-documents",
            json={
                "title": "木渎小志",
                "edition": "民国十二年刻本",
                "source_institution": "苏州地方文献馆",
                "source_type": "gazetteer",
                "source_level": "A",
                "holder": "星羲项目资料组",
            },
        ).json()
        response = client.post(
            f"/api/source-documents/{created['id']}/files",
            files={"files": ("mudu.pdf", b"%PDF-1.7\nsynthetic stage 10 file", "application/pdf")},
        )
        listing = client.get(f"/api/source-documents/{created['id']}/files")

    assert response.status_code == 200
    assert response.json()["success_count"] == 1
    assert response.json()["failure_count"] == 0
    uploaded = response.json()["items"][0]
    assert uploaded["status"] == "uploaded"
    assert uploaded["filename"] == "mudu.pdf"
    assert uploaded["file"]["document_id"] == created["id"]
    assert uploaded["file"]["mime_type"] == "application/pdf"
    assert uploaded["file"]["size"] == len(b"%PDF-1.7\nsynthetic stage 10 file")
    assert uploaded["file"]["uploaded_by"] == str(ADMIN_ID)
    assert listing.status_code == 200
    assert listing.json() == [uploaded["file"]]


def test_batch_upload_keeps_valid_image_when_forged_pdf_fails(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        created = client.post(
            "/api/source-documents",
            json={
                "title": "香溪图档",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()
        response = client.post(
            f"/api/source-documents/{created['id']}/files",
            files=[
                ("files", ("map.png", b"\x89PNG\r\n\x1a\nsynthetic image", "image/png")),
                ("files", ("forged.pdf", b"this is not a pdf", "application/pdf")),
            ],
        )
        listing = client.get(f"/api/source-documents/{created['id']}/files")

    assert response.status_code == 200
    assert response.json()["success_count"] == 1
    assert response.json()["failure_count"] == 1
    assert [item["status"] for item in response.json()["items"]] == ["uploaded", "failed"]
    assert response.json()["items"][0]["file"]["mime_type"] == "image/png"
    assert "invalid" in response.json()["items"][1]["error"].lower()
    assert [item["original_filename"] for item in listing.json()] == ["map.png"]


def test_empty_and_oversized_files_fail_without_leaving_staging_files(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    staging_dir = tmp_path / "staging"
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_source_upload_limits] = lambda: source_documents.SourceUploadLimits(
        max_files=10,
        max_file_size=16,
        max_total_size=32,
    )
    app.dependency_overrides[source_documents.get_source_upload_staging_dir] = lambda: staging_dir
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        created = client.post(
            "/api/source-documents",
            json={
                "title": "上传边界测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()
        response = client.post(
            f"/api/source-documents/{created['id']}/files",
            files=[
                ("files", ("empty.pdf", b"", "application/pdf")),
                ("files", ("large.pdf", b"%PDF-1.7\n" + b"x" * 32, "application/pdf")),
            ],
        )

    assert response.status_code == 200
    assert response.json()["success_count"] == 0
    assert response.json()["failure_count"] == 2
    assert [item["error_code"] for item in response.json()["items"]] == ["empty_file", "file_too_large"]
    assert not staging_dir.exists() or list(staging_dir.iterdir()) == []


def test_database_binding_failure_removes_newly_stored_object(tmp_path):
    class FailingSourceFileRepository(InMemorySourceFileRepository):
        async def attach(self, source_file, metadata):
            raise RuntimeError("synthetic database failure")

    documents = InMemorySourceDocumentRepository()
    source_files = FailingSourceFileRepository()
    object_root = tmp_path / "objects"
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(object_root)
    app.dependency_overrides[source_documents.get_source_upload_staging_dir] = lambda: tmp_path / "staging"
    app.include_router(source_documents.router)

    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/source-documents",
            json={
                "title": "失败回滚测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()
        response = client.post(
            f"/api/source-documents/{created['id']}/files",
            files={"files": ("rollback.pdf", b"%PDF-1.7\nrollback", "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["error_code"] == "storage_failed"
    remaining_objects = [path for path in object_root.rglob("*") if path.is_file() and path.name != "deletion-audit.jsonl"]
    assert remaining_objects == []


def test_source_upload_limits_and_admin_boundary(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    limits = source_documents.SourceUploadLimits(max_files=3, max_file_size=1024, max_total_size=2048)

    admin_app = make_authed_test_app(user_factory=_admin_user)
    admin_app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    admin_app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    admin_app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    admin_app.dependency_overrides[source_documents.get_source_upload_limits] = lambda: limits
    admin_app.include_router(source_documents.router)

    with TestClient(admin_app) as client:
        limits_response = client.get("/api/source-documents/upload/limits")
        missing = client.post(
            "/api/source-documents/source-missing/files",
            files={"files": ("missing.pdf", b"%PDF-1.7\nmissing", "application/pdf")},
        )

    regular_app = make_authed_test_app(
        user_factory=lambda: User(
            id=UUID("99999999-8888-7777-6666-555555555555"),
            email="user@example.com",
            password_hash="x",
            system_role="user",
        )
    )
    regular_app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    regular_app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    regular_app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    regular_app.include_router(source_documents.router)
    with TestClient(regular_app) as client:
        forbidden_upload = client.post(
            "/api/source-documents/source-missing/files",
            files={"files": ("forbidden.pdf", b"%PDF-1.7\nforbidden", "application/pdf")},
        )
        forbidden_list = client.get("/api/source-documents/source-missing/files")

    assert limits_response.status_code == 200
    assert limits_response.json() == {
        "max_files": 3,
        "max_file_size": 1024,
        "max_total_size": 2048,
        "allowed_extensions": [".pdf", ".png", ".jpg", ".jpeg", ".docx", ".txt", ".md", ".markdown"],
    }
    assert missing.status_code == 404
    assert forbidden_upload.status_code == 403
    assert forbidden_list.status_code == 403


def test_same_content_with_different_name_reports_existing_file(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_source_upload_staging_dir] = lambda: tmp_path / "staging"
    app.include_router(source_documents.router)

    content = b"%PDF-1.7\nsame stage 11 content"
    with TestClient(app) as client:
        document = client.post(
            "/api/source-documents",
            json={
                "title": "重复文件测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()
        first = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("first.pdf", content, "application/pdf")},
        )
        duplicate = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("renamed.pdf", content, "application/pdf")},
        )
        listing = client.get(f"/api/source-documents/{document['id']}/files")

    assert first.json()["success_count"] == 1
    assert duplicate.status_code == 200
    assert duplicate.json()["success_count"] == 0
    assert duplicate.json()["items"][0]["error_code"] == "duplicate_file"
    assert duplicate.json()["items"][0]["existing_file"]["id"] == first.json()["items"][0]["file"]["id"]
    assert len(listing.json()) == 1


def test_admin_can_reference_existing_bytes_from_another_source(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_source_upload_staging_dir] = lambda: tmp_path / "staging"
    app.include_router(source_documents.router)

    content = b"%PDF-1.7\nshared stage 11 content"
    source_body = {
        "title": "跨来源引用测试",
        "edition": "测试版",
        "source_institution": "测试机构",
        "source_type": "archive",
        "source_level": "B",
        "holder": "测试资料组",
    }
    with TestClient(app) as client:
        first_source = client.post("/api/source-documents", json=source_body).json()
        second_source = client.post(
            "/api/source-documents",
            json={**source_body, "edition": "另一登记版本"},
        ).json()
        first = client.post(
            f"/api/source-documents/{first_source['id']}/files",
            files={"files": ("first.pdf", content, "application/pdf")},
        ).json()["items"][0]["file"]
        referenced_response = client.post(
            f"/api/source-documents/{second_source['id']}/files",
            data={"duplicate_policy": "reference_existing"},
            files={"files": ("renamed.pdf", content, "application/pdf")},
        )

    assert referenced_response.status_code == 200
    referenced = referenced_response.json()["items"][0]["file"]
    assert referenced_response.json()["success_count"] == 1
    assert referenced["document_id"] == second_source["id"]
    assert referenced["object_key"] == first["object_key"]
    assert referenced["duplicate_of_file_id"] == first["id"]
    assert referenced["version_of_file_id"] is None


def test_same_name_with_different_content_can_create_new_version(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_source_upload_staging_dir] = lambda: tmp_path / "staging"
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        document = client.post(
            "/api/source-documents",
            json={
                "title": "文件版本测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()
        first = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("source.pdf", b"%PDF-1.7\nversion one", "application/pdf")},
        ).json()["items"][0]["file"]
        second_response = client.post(
            f"/api/source-documents/{document['id']}/files",
            data={
                "duplicate_policy": "new_version",
                "version_of_file_id": first["id"],
            },
            files={"files": ("source.pdf", b"%PDF-1.7\nversion two", "application/pdf")},
        )

    assert second_response.status_code == 200
    second = second_response.json()["items"][0]["file"]
    assert second_response.json()["success_count"] == 1
    assert second["object_key"] != first["object_key"]
    assert second["sha256"] != first["sha256"]
    assert second["version_of_file_id"] == first["id"]
    assert second["duplicate_of_file_id"] is None


def test_same_name_with_different_content_requires_explicit_version_choice(tmp_path):
    documents = InMemorySourceDocumentRepository()
    source_files = InMemorySourceFileRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: documents
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: source_files
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: LocalObjectStorage(tmp_path / "objects")
    app.dependency_overrides[source_documents.get_source_upload_staging_dir] = lambda: tmp_path / "staging"
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        document = client.post(
            "/api/source-documents",
            json={
                "title": "同名文件测试",
                "edition": "测试版",
                "source_institution": "测试机构",
                "source_type": "archive",
                "source_level": "B",
                "holder": "测试资料组",
            },
        ).json()
        first = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("source.pdf", b"%PDF-1.7\nfirst content", "application/pdf")},
        ).json()["items"][0]["file"]
        conflict = client.post(
            f"/api/source-documents/{document['id']}/files",
            files={"files": ("source.pdf", b"%PDF-1.7\ndifferent content", "application/pdf")},
        )

    assert conflict.status_code == 200
    assert conflict.json()["success_count"] == 0
    assert conflict.json()["items"][0]["error_code"] == "same_name_different_content"
    assert conflict.json()["items"][0]["existing_file"]["id"] == first["id"]
