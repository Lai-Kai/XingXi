from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from wu_culture.releases import (
    KnowledgeReleaseGateError,
    KnowledgeReleaseItem,
    KnowledgeReleasePreparationError,
    KnowledgeReleaseState,
    ReleaseAction,
    ReleaseStatus,
    build_knowledge_release,
)

from app.gateway.auth.models import User
from app.gateway.routers import knowledge_releases
from app.gateway.services import resolve_active_knowledge_release_metadata

NOW = datetime(2026, 7, 21, 17, 0, tzinfo=UTC)


def _user(role: str = "admin") -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email=f"{role}@example.com",
        password_hash="x",
        system_role=role,
    )


class _ReleaseRepository:
    def __init__(self) -> None:
        self.releases = []
        self.state = KnowledgeReleaseState(active_release_id=None, active_version=None, state_version=0)
        self.events = []

    async def publish(self, request, *, actor_id, created_at):
        release = build_knowledge_release(
            release_id=f"release-{len(self.releases) + 1}",
            version_number=len(self.releases) + 1,
            release_notes=request.release_notes,
            items=(
                KnowledgeReleaseItem(
                    ordinal=0,
                    document_id="document-1",
                    source_file_id="file-1",
                    chunk_set_id=request.chunk_set_ids[0],
                    chunk_id=f"chunk-{len(self.releases) + 1}",
                    content_sha256="a" * 64,
                    cleaned_page_ids=("page-1",),
                ),
            ),
            created_by=actor_id,
            created_at=created_at,
            status=ReleaseStatus.ACTIVE,
        )
        self.releases.append(release)
        self.state = KnowledgeReleaseState(
            active_release_id=release.id,
            active_version=release.version,
            state_version=self.state.state_version + 1,
            updated_by=actor_id,
            updated_at=created_at,
        )
        self.events.append(ReleaseAction.PUBLISH)
        return release

    async def list_releases(self):
        return self.releases

    async def get(self, release_id):
        return next((release for release in self.releases if release.id == release_id), None)

    async def get_state(self):
        return self.state

    async def get_active(self):
        return await self.get(self.state.active_release_id)

    async def list_events(self):
        return []

    async def rollback(self, request, *, actor_id, changed_at):
        target = await self.get(request.target_release_id)
        self.state = KnowledgeReleaseState(
            active_release_id=target.id,
            active_version=target.version,
            state_version=self.state.state_version + 1,
            updated_by=actor_id,
            updated_at=changed_at,
        )
        return self.state


class _PreparationRepository(_ReleaseRepository):
    async def publish(self, request, *, actor_id, created_at):
        raise KnowledgeReleasePreparationError(
            "release-failed",
            "knowledge release preparation failed: asset query failed",
        )

    async def retry(self, release_id, request, *, actor_id, changed_at):
        assert release_id == "release-failed"
        assert request.expected_state_version == 0
        return build_knowledge_release(
            release_id=release_id,
            version_number=1,
            release_notes="重试成功",
            items=(
                KnowledgeReleaseItem(
                    ordinal=0,
                    document_id="document-1",
                    source_file_id="file-1",
                    chunk_set_id="chunk-set-1",
                    chunk_id="chunk-1",
                    content_sha256="a" * 64,
                    cleaned_page_ids=("page-1",),
                ),
            ),
            created_by=actor_id,
            created_at=changed_at,
            status=ReleaseStatus.ACTIVE,
        ).model_copy(update={"preparation_attempts": 2})

    async def activate(self, request, *, actor_id, changed_at):
        raise KnowledgeReleaseGateError("knowledge release is failed, not ready")


def test_admin_publishes_lists_and_stamps_active_release_metadata() -> None:
    repository = _ReleaseRepository()
    app = make_authed_test_app(user_factory=_user)
    app.dependency_overrides[knowledge_releases.get_knowledge_release_repository] = lambda: repository
    app.include_router(knowledge_releases.router)

    with TestClient(app) as client:
        published = client.post(
            "/api/knowledge-releases",
            json={"chunk_set_ids": ["chunk-set-1"], "release_notes": "首版", "expected_state_version": 0},
        )
        listed = client.get("/api/knowledge-releases")
        state = client.get("/api/knowledge-releases/state")

    assert published.status_code == 201
    assert listed.json()[0]["version"] == "v1"
    assert state.json()["active_release_id"] == "release-1"
    metadata = asyncio.run(resolve_active_knowledge_release_metadata(repository))
    assert metadata == {
        "knowledge_release_id": "release-1",
        "knowledge_release_version": "v1",
        "knowledge_release_manifest_sha256": published.json()["manifest_sha256"],
        "knowledge_release_scope": "public",
    }


def test_non_admin_cannot_manage_releases() -> None:
    app = make_authed_test_app(user_factory=lambda: _user("user"))
    app.dependency_overrides[knowledge_releases.get_knowledge_release_repository] = _ReleaseRepository
    app.include_router(knowledge_releases.router)

    with TestClient(app) as client:
        response = client.get("/api/knowledge-releases/state")

    assert response.status_code == 403


def test_preparation_failure_is_retryable_and_unready_activation_is_blocked() -> None:
    repository = _PreparationRepository()
    app = make_authed_test_app(user_factory=_user)
    app.dependency_overrides[
        knowledge_releases.get_knowledge_release_repository
    ] = lambda: repository
    app.include_router(knowledge_releases.router)

    with TestClient(app) as client:
        failed = client.post(
            "/api/knowledge-releases",
            json={
                "chunk_set_ids": ["chunk-set-1"],
                "release_notes": "失败版本",
                "expected_state_version": 0,
            },
        )
        retry = client.post(
            "/api/knowledge-releases/release-failed/retry",
            json={"expected_state_version": 0},
        )
        blocked = client.post(
            "/api/knowledge-releases/activate",
            json={
                "release_id": "release-failed",
                "expected_state_version": 0,
                "reason": "不应激活",
            },
        )

    assert failed.status_code == 503
    assert failed.json()["detail"] == {
        "code": "release_preparation_failed",
        "message": "knowledge release preparation failed: asset query failed",
        "release_id": "release-failed",
        "retryable": True,
    }
    assert retry.status_code == 200
    assert retry.json()["status"] == "active"
    assert retry.json()["preparation_attempts"] == 2
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "release_conflict"
