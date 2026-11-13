"""Test manual and automatic question APIs together on the actual Gateway."""

from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.gateway.app import create_app
from app.gateway.evaluations.api import case_repository
from app.gateway.routers.operations import get_operations_repository

ROOT = "/api/operations/evaluations"


def test_evaluation_routes_have_no_duplicate_method_and_path():
    routes = Counter((method, route.path) for route in create_app().routes if getattr(route, "path", "").startswith(ROOT) for method in route.methods)
    assert {key: count for key, count in routes.items() if count > 1} == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "user"])
async def test_real_gateway_keeps_manual_cases_and_agent_questions_independent(role):
    app = create_app()
    app.user_middleware.clear()
    manual = AsyncMock()
    manual.list_evaluation_cases.return_value = []
    automatic = AsyncMock()
    automatic.list.return_value = []
    app.dependency_overrides[get_operations_repository] = lambda: manual
    app.dependency_overrides[case_repository] = lambda: automatic

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user = SimpleNamespace(id="reviewer", system_role=role, business_role="government")
        return await call_next(request)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(ROOT + "/cases")
        assert response.status_code == 200
        assert response.json() == []
        response = await client.get(ROOT + "/questions")
        assert response.status_code == 200, response.text
        collection = response.json()
        assert len(collection["cases"]) == 30
        assert len(collection["methods"]) == 10
        assert all(case["question"] for case in collection["cases"])
        assert all(method["description"] for method in collection["methods"])
        response = await client.post(ROOT + "/questions", json={"title": "新问题", "question": "测试桥在哪里？", "scenario": "grounded", "mode": "pro"})
        if role == "admin":
            assert response.status_code == 201, response.text
            assert response.json()["builtin"] is False
            assert response.json()["required_tool"] == "search_sources"
            automatic.create.assert_awaited_once()
        else:
            assert response.status_code == 403
            automatic.create.assert_not_awaited()
        for method, path in [("DELETE", "/questions/grounded-pro"), ("POST", "/questions/grounded-pro/restore")]:
            response = await client.request(method, ROOT + path)
            assert response.status_code == (200 if role == "admin" else 403), response.text
        manual.list_evaluation_cases.assert_awaited_once()
        manual.create_evaluation_case.assert_not_awaited()
