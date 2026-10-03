from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.evaluations.api import repository, router


def _app(role: str, repo):
    app = FastAPI()
    app.state.evaluation_service = object()
    app.include_router(router)
    app.dependency_overrides[repository] = lambda: repo

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user = SimpleNamespace(id="operator", system_role=role, business_role="government")
        return await call_next(request)

    return app


def test_governance_reader_cannot_execute_cancel_rerun_or_review():
    repo = AsyncMock()
    with TestClient(_app("user", repo)) as client:
        assert client.get("/api/operations/evaluations/catalog").status_code == 200
        for path, payload in [
            ("/executions", {"request_key": "request-1"}),
            ("/executions/run/cancel", {}),
            ("/executions/run/rerun", {"request_key": "request-2"}),
            ("/executions/run/reviews", {"case_id": "one", "decision": "confirmed", "note": "复核"}),
        ]:
            assert client.post("/api/operations/evaluations" + path, json=payload).status_code == 403
    repo.create.assert_not_awaited()
    repo.cancel.assert_not_awaited()


def test_admin_start_freezes_server_cases_and_rejects_client_model_or_release(monkeypatch):
    repo = AsyncMock()
    repo.create.return_value = {"id": "batch", "status": "queued"}
    monkeypatch.setattr("app.gateway.evaluations.api.environment_snapshot", lambda: {"version": "test"})
    with TestClient(_app("admin", repo)) as client:
        assert client.post("/api/operations/evaluations/executions", json={"request_key": "request-1", "release_id": "forged"}).status_code == 422
        assert client.post("/api/operations/evaluations/executions", json={"request_key": "request-2", "execution_mode": "live"}).status_code == 422
        response = client.post("/api/operations/evaluations/executions", json={"request_key": "request-3", "smoke": True})
        assert response.status_code == 202
    assert len(repo.create.call_args.kwargs["cases"]) == 6


def test_export_uses_persisted_report_and_disables_caching():
    repo = AsyncMock()
    repo.get.return_value = {"id": "batch", "status": "error", "total": 1, "passed": 0, "results": []}
    with TestClient(_app("user", repo)) as client:
        response = client.get("/api/operations/evaluations/executions/batch/export?format=json")
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
