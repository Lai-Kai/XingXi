from __future__ import annotations

from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture.repositories import InMemorySourceDocumentRepository

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


def _regular_user() -> User:
    return User(
        id=UUID("99999999-8888-7777-6666-555555555555"),
        email="user@example.com",
        password_hash="x",
        system_role="user",
    )


def test_admin_can_register_same_title_as_distinct_editions():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)

    base = {
        "title": "木渎小志",
        "source_institution": "苏州地方文献馆",
        "source_type": "gazetteer",
        "source_level": "A",
        "holder": "星羲项目资料组",
    }
    with TestClient(app) as client:
        first = client.post("/api/source-documents", json={**base, "edition": "民国十二年刻本"})
        second = client.post("/api/source-documents", json={**base, "edition": "二〇〇二年整理本"})
        third = client.post(
            "/api/source-documents",
            json={
                **base,
                "edition": "民国十二年刻本",
                "source_institution": "木渎地方文献中心",
            },
        )
        listing = client.get("/api/source-documents")
        detail = client.get(f"/api/source-documents/{first.json()['id']}")

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 201
    assert len({first.json()["id"], second.json()["id"], third.json()["id"]}) == 3
    assert [item["edition"] for item in listing.json()] == ["民国十二年刻本", "二〇〇二年整理本", "民国十二年刻本"]
    assert listing.json()[2]["source_institution"] == "木渎地方文献中心"
    assert detail.json() == first.json()
    assert first.json()["status"] == "registered"
    assert first.json()["copyright_status"] == "unknown"
    assert first.json()["created_by"] == str(ADMIN_ID)
    assert first.json()["updated_by"] == str(ADMIN_ID)
    assert first.json()["created_at"]
    assert first.json()["updated_at"]


def test_admin_can_register_unplanned_document_with_custom_source_type():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)

    payload = {
        "title": "震泽商会会员名录",
        "edition": "民国二十三年抄本",
        "source_institution": "私人授权收藏",
        "source_type": "other",
        "source_type_label": "商会名录",
        "source_level": "B",
        "holder": "资料授权人",
    }
    with TestClient(app) as client:
        created = client.post("/api/source-documents", json=payload)
        missing_label = client.post(
            "/api/source-documents",
            json={key: value for key, value in payload.items() if key != "source_type_label"},
        )
        invalid_standard_label = client.post(
            "/api/source-documents",
            json={**payload, "source_type": "archive"},
        )

    assert created.status_code == 201
    assert created.json()["title"] == "震泽商会会员名录"
    assert created.json()["source_type"] == "other"
    assert created.json()["source_type_label"] == "商会名录"
    assert missing_label.status_code == 422
    assert invalid_standard_label.status_code == 422


def test_admin_can_change_custom_source_type_back_to_standard() -> None:
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)

    payload = {
        "title": "震泽商会会员名录",
        "edition": "民国二十三年抄本",
        "source_institution": "私人授权收藏",
        "source_type": "other",
        "source_type_label": "商会名录",
        "source_level": "B",
        "holder": "资料授权人",
    }
    with TestClient(app) as client:
        created = client.post("/api/source-documents", json=payload).json()
        changed = client.patch(
            f"/api/source-documents/{created['id']}",
            json={"source_type": "archive"},
        )
        invalid_label_only = client.patch(
            f"/api/source-documents/{created['id']}",
            json={"source_type_label": "不应保留"},
        )

    assert changed.status_code == 200
    assert changed.json()["source_type"] == "archive"
    assert changed.json()["source_type_label"] is None
    assert invalid_label_only.status_code == 422


def test_admin_can_page_and_search_registered_sources():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)
    base = {
        "edition": "合成测试版",
        "source_institution": "测试馆",
        "source_type": "archive",
        "source_level": "B",
        "holder": "测试馆",
    }
    with TestClient(app) as client:
        client.post("/api/source-documents", json={**base, "title": "木渎商号索引"})
        client.post("/api/source-documents", json={**base, "title": "苏州街巷索引"})
        response = client.get("/api/source-documents/page", params={"query": "木渎", "limit": 10, "offset": 0})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "木渎商号索引"


def test_admin_update_preserves_stable_id_and_creation_audit():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
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
        response = client.patch(
            f"/api/source-documents/{created['id']}",
            json={
                "edition": "民国十二年刻本影印本",
                "source_institution": "木渎地方文献中心",
                "source_level": "B",
            },
        )

    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["created_by"] == created["created_by"]
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_by"] == str(ADMIN_ID)
    assert updated["updated_at"] >= created["updated_at"]
    assert updated["edition"] == "民国十二年刻本影印本"
    assert updated["source_institution"] == "木渎地方文献中心"
    assert updated["source_level"] == "B"


def test_registration_rejects_missing_fields_invalid_level_and_unknown_fields():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_admin_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)

    with TestClient(app) as client:
        missing = client.post(
            "/api/source-documents",
            json={
                "title": "木渎小志",
                "source_type": "gazetteer",
                "source_level": "A",
            },
        )
        invalid_level = client.post(
            "/api/source-documents",
            json={
                "title": "木渎小志",
                "edition": "民国十二年刻本",
                "source_institution": "苏州地方文献馆",
                "source_type": "gazetteer",
                "source_level": "F",
                "holder": "星羲项目资料组",
            },
        )
        unknown = client.post(
            "/api/source-documents",
            json={
                "title": "木渎小志",
                "edition": "民国十二年刻本",
                "source_institution": "苏州地方文献馆",
                "source_type": "gazetteer",
                "source_level": "A",
                "holder": "星羲项目资料组",
                "file_content": "must not be accepted in stage 08",
            },
        )

    assert missing.status_code == 422
    assert invalid_level.status_code == 422
    assert unknown.status_code == 422


def test_source_document_routes_require_admin():
    repository = InMemorySourceDocumentRepository()
    app = make_authed_test_app(user_factory=_regular_user)
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: repository
    app.include_router(source_documents.router)
    valid_body = {
        "title": "木渎小志",
        "edition": "民国十二年刻本",
        "source_institution": "苏州地方文献馆",
        "source_type": "gazetteer",
        "source_level": "A",
        "holder": "星羲项目资料组",
    }

    with TestClient(app) as client:
        responses = [
            client.post("/api/source-documents", json=valid_body),
            client.get("/api/source-documents"),
            client.get("/api/source-documents/source-missing"),
            client.patch("/api/source-documents/source-missing", json={"edition": "其他版本"}),
        ]

    assert [response.status_code for response in responses] == [403, 403, 403, 403]
    assert all("Admin privileges" in response.json()["detail"] for response in responses)


def test_gateway_mounts_source_document_api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    from deerflow.config.app_config import reset_app_config

    reset_app_config()
    from app.gateway.app import create_app

    paths = create_app().openapi()["paths"]

    assert "/api/source-documents" in paths
    assert set(paths["/api/source-documents"]) >= {"get", "post"}
    assert set(paths["/api/source-documents/{document_id}"]) >= {"get", "patch"}
    assert set(paths["/api/source-documents/{document_id}/authorization"]) >= {"put"}
    assert set(paths["/api/source-documents/{document_id}/authorization/history"]) >= {"get"}
    assert set(paths["/api/source-documents/{document_id}/files"]) >= {"get", "post"}
    assert set(paths["/api/source-documents/upload/limits"]) >= {"get"}
    assert set(paths["/api/public/source-documents/{document_id}/access"]) >= {"get"}
