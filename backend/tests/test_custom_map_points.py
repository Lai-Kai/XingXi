from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway import map_points_store
from app.gateway.reconstructions.config import ReconstructionConfig
from app.gateway.reconstructions.service import ReconstructionService
from app.gateway.reconstructions.store import JobStore
from app.gateway.reconstructions.store import metadata as job_metadata
from app.gateway.routers import custom_map_points, map_models


@pytest_asyncio.fixture
async def setup(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'points.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(map_points_store.metadata.create_all)
        await connection.run_sync(job_metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(custom_map_points.router)
    app.include_router(map_models.router)
    user = SimpleNamespace(id="admin", system_role="admin")

    def current_user():
        if user.system_role is None:
            raise HTTPException(401, "请先登录")
        return user

    store = map_points_store.MapPointsStore(sessions)
    service = ReconstructionService(ReconstructionConfig(local_root=tmp_path / "models"), JobStore(sessions), SimpleNamespace())
    app.dependency_overrides[custom_map_points.get_current_user_from_request] = current_user
    app.dependency_overrides[custom_map_points.get_store] = lambda: store
    app.dependency_overrides[map_models.get_service] = lambda: service
    app.dependency_overrides[map_models.map_points.get_versioned_catalog_source] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, user, sessions
    await service.close()
    await engine.dispose()


def body(**changes):
    return {"name": " 新建古桥 ", "lon": 120.506, "lat": 31.253, "request_id": "first", **changes}


@pytest.mark.asyncio
async def test_persist_and_reload_named_point_without_publishing_knowledge(setup):
    client, _, sessions = setup
    response = await client.post("/api/map/custom-points", json=body())
    assert response.status_code == 201, response.text
    point = response.json()
    assert point["name"] == "新建古桥"
    assert (point["lon"], point["lat"], point["coordinate_system"]) == (120.506, 31.253, "WGS84")
    assert point["record_kind"] == "custom"
    assert point["evidence"] == [] and point["release_id"] is None and point["review_status"] is None
    assert "owner_id" not in point and "request_id" not in point
    assert (await client.get("/api/map/custom-points")).json() == [point]
    restored = map_points_store.MapPointsStore(sessions)
    assert custom_map_points.public_point((await restored.list())[0]).model_dump(mode="json") == point


@pytest.mark.asyncio
async def test_retry_is_idempotent_and_changed_payload_conflicts(setup):
    client, _, _ = setup
    first = await client.post("/api/map/custom-points", json=body())
    retry = await client.post("/api/map/custom-points", json=body())
    assert first.json()["id"] == retry.json()["id"]
    assert (await client.post("/api/map/custom-points", json=body(lon=120.507))).status_code == 409
    assert len((await client.get("/api/map/custom-points")).json()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"name": "   "}, {"name": "a" * 121}, {"name": "bad\x00name"}, {"lon": 181}, {"lon": -181}, {"lat": 91}, {"lat": -91}, {"lat": "NaN"}, {"lon": True}, {"entity_id": "forged"}])
async def test_invalid_input_is_not_saved(setup, changes):
    client, _, _ = setup
    assert (await client.post("/api/map/custom-points", json=body(**changes))).status_code == 422
    assert (await client.get("/api/map/custom-points")).json() == []


@pytest.mark.asyncio
async def test_only_admin_can_create_but_signed_in_readers_can_read(setup):
    client, user, _ = setup
    assert (await client.post("/api/map/custom-points", json=body())).status_code == 201
    user.system_role = "user"
    assert (await client.post("/api/map/custom-points", json=body(request_id="second"))).status_code == 403
    assert len((await client.get("/api/map/custom-points")).json()) == 1
    user.system_role = None
    assert (await client.get("/api/map/custom-points")).status_code == 401
    assert (await client.post("/api/map/custom-points", json=body())).status_code == 401


@pytest.mark.asyncio
async def test_created_point_can_bind_and_read_a_persistent_model(setup):
    client, _, _ = setup
    point = (await client.post("/api/map/custom-points", json=body())).json()
    ply = b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n0 0 0 255 0 0\n"
    response = await client.post("/api/map/model-assets", data={"point_id": point["id"], "title": "新点位模型"}, files={"file": ("color.ply", ply)})
    assert response.status_code == 201, response.text
    model = response.json()
    assert (model["point_id"], model["entity_id"]) == (point["id"], point["entity_id"])
    assert (await client.get(model["preview_url"])).content == ply
    assert (await client.get("/api/map/model-assets")).json() == [model]
