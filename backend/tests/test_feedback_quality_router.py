from __future__ import annotations

from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.gateway.auth.models import User
from app.gateway.auth.roles import BusinessCapability
from app.gateway.routers import feedback


class _FeedbackRepo:
    async def list_quality_queue(self, **_kwargs):
        return (
            [
                {
                    "feedback_id": "feedback-1",
                    "run_id": "run-1",
                    "thread_id": "thread-1",
                    "user_id": "user-1",
                    "rating": -1,
                    "comment": "页码不符",
                    "category": "citation_error",
                    "status": "submitted",
                    "created_at": "2026-07-28T00:00:00+00:00",
                }
            ],
            1,
        )

    async def review(self, feedback_id: str, **kwargs):
        return {
            "feedback_id": feedback_id,
            "run_id": "run-1",
            "thread_id": "thread-1",
            "user_id": "user-1",
            "rating": -1,
            "comment": "页码不符",
            "category": "citation_error",
            "status": kwargs["status"],
            "assignee_id": kwargs["assignee_id"],
            "review_note": kwargs["review_note"],
            "created_at": "2026-07-28T00:00:00+00:00",
        }


def _user(system_role: str = "user") -> User:
    return User(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        email="reviewer@example.com",
        password_hash="x",
        system_role=system_role,
    )


def _app(system_role: str):
    app = make_authed_test_app(user_factory=lambda: _user(system_role))
    app.state.feedback_repo = _FeedbackRepo()
    app.include_router(feedback.router)
    return app


def test_administrator_can_list_and_review_quality_feedback():
    with TestClient(_app("admin")) as client:
        listing = client.get("/api/threads/feedback/quality-queue")
        reviewed = client.patch(
            "/api/threads/feedback/feedback-1/review",
            json={"status": "reviewing", "review_note": "核对原始页"},
        )

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewing"
    assert reviewed.json()["assignee_id"] == str(_user("admin").id)


def test_public_user_cannot_open_quality_feedback_queue():
    with TestClient(_app("user")) as client:
        response = client.get("/api/threads/feedback/quality-queue")

    assert response.status_code == 403


def test_quality_read_only_user_cannot_change_review_status(monkeypatch):
    from app.gateway.auth import roles

    monkeypatch.setattr(
        roles,
        "capabilities_for",
        lambda *_args, **_kwargs: frozenset({BusinessCapability.QUALITY_READ}),
    )
    with TestClient(_app("user")) as client:
        listing = client.get("/api/threads/feedback/quality-queue")
        reviewed = client.patch(
            "/api/threads/feedback/feedback-1/review",
            json={"status": "accepted", "review_note": "不应写入"},
        )

    assert listing.status_code == 200
    assert reviewed.status_code == 403
