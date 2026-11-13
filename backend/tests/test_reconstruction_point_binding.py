from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from test_reconstructions import files
from test_reconstructions import fixture as fixture

from app.gateway.routers import map_models


@pytest.mark.asyncio
async def test_unknown_point_is_rejected_before_persistent_copy_or_ssh(fixture):
    client, service, remote, app = fixture
    app.dependency_overrides[map_models.get_model_points] = lambda: {}
    response = await client.post("/api/reconstructions", data={"title": "未知点位", "point_id": "forged-point", "point_name": "伪造名称"}, files=files())
    assert response.status_code == 404, response.text
    assert remote.starts == []
    assert await service.store.list() == []
    assert list(service.config.local_root.glob("*/source")) == []


@pytest.mark.asyncio
async def test_bound_reconstruction_uses_server_point_name_and_entity_and_survives_restart(fixture):
    client, service, remote, app = fixture
    app.dependency_overrides[map_models.get_model_points] = lambda: {"point": SimpleNamespace(id="point", entity_id="canonical-entity", name="服务器古桥")}
    response = await client.post("/api/reconstructions", data={"title": "新建模型", "point_id": "point", "point_name": "伪造名称", "entity_id": "forged-entity", "request_id": "bound"}, files=files())
    assert response.status_code == 202, response.text
    job = response.json()
    assert (job["point_id"], job["point_name"], job["entity_id"]) == ("point", "服务器古桥", "canonical-entity")
    await asyncio.gather(*list(service.tasks.values()))
    stored = await service.store.get(job["id"])
    assert (stored["point_id"], stored["point_name"], stored["entity_id"]) == ("point", "服务器古桥", "canonical-entity")
    retried = await client.post("/api/reconstructions", data={"title": "新建模型", "point_id": "point", "point_name": "另一个浏览器名称", "request_id": "bound"}, files=files())
    assert retried.json()["id"] == job["id"]
    assert remote.starts == [job["id"]]


@pytest.mark.asyncio
async def test_explicit_standalone_reconstruction_does_not_accept_an_unbound_point_name(fixture):
    client, service, _, app = fixture
    app.dependency_overrides[map_models.get_model_points] = lambda: {}
    response = await client.post("/api/reconstructions", data={"title": "独立任务", "point_name": "伪造绑定", "entity_id": "forged"}, files=files())
    assert response.status_code == 202, response.text
    stored = await service.store.get(response.json()["id"])
    assert stored["point_id"] is None and stored["point_name"] is None
    assert stored.get("entity_id") is None
