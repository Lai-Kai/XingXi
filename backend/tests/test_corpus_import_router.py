from __future__ import annotations

from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.gateway.auth.models import User
from app.gateway.routers import corpus_imports

ADMIN_ID = UUID("11111111-2222-3333-4444-555555555555")
USER_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


class _Repository:
    async def list_batches(self):
        return [
            {
                "id": "batch-1",
                "corpus_root_id": "fuxianzhi",
                "manifest_sha256": "a" * 64,
                "status": "completed",
                "created_by": "admin-1",
                "created_at": "2026-08-22T00:00:00Z",
                "completed_at": "2026-08-22T00:10:00Z",
                "item_count": 1,
                "page_count": 394,
                "quality_issue_count": 592,
            }
        ]

    async def list_items(self, batch_id: str):
        assert batch_id == "batch-1"
        return [
            {
                "id": "item-1",
                "batch_id": batch_id,
                "bundle_id": "b" * 64,
                "document_id": "doc-1",
                "source_file_id": "file-1",
                "chunk_set_id": "chunks-1",
                "page_count": 394,
                "quality_issue_count": 592,
                "status": "completed",
                "imported_by": "admin-1",
                "imported_at": "2026-08-22T00:10:00Z",
            }
        ]

    async def list_quality_issues(self, item_id: str, *, limit: int, offset: int):
        assert item_id == "item-1"
        assert (limit, offset) == (100, 0)
        return []


def _user(system_role: str) -> User:
    return User(
        id=ADMIN_ID if system_role == "admin" else USER_ID,
        email=f"{system_role}@example.com",
        password_hash="x",
        system_role=system_role,
    )


def test_admin_reads_corpus_import_batches_and_items():
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.dependency_overrides[corpus_imports.get_corpus_import_repository] = _Repository
    app.include_router(corpus_imports.router)

    with TestClient(app) as client:
        batches = client.get("/api/corpus-imports")
        items = client.get("/api/corpus-imports/batch-1/items")

    assert batches.status_code == 200
    assert batches.json()[0]["page_count"] == 394
    assert items.status_code == 200
    assert items.json()[0]["quality_issue_count"] == 592


def test_regular_user_cannot_read_corpus_import_operations():
    app = make_authed_test_app(user_factory=lambda: _user("user"))
    app.dependency_overrides[corpus_imports.get_corpus_import_repository] = _Repository
    app.include_router(corpus_imports.router)

    with TestClient(app) as client:
        response = client.get("/api/corpus-imports")

    assert response.status_code == 403
