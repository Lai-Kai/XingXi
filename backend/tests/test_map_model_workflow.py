from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway.map_points_store import MapPointsStore
from app.gateway.map_points_store import metadata as point_metadata
from app.gateway.reconstructions.config import ReconstructionConfig
from app.gateway.reconstructions.service import ReconstructionService
from app.gateway.reconstructions.store import JobStore
from app.gateway.reconstructions.store import metadata as job_metadata
from app.gateway.routers import custom_map_points, map_models, reconstructions

PLY = b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n0 0 0 255 0 0\n"


class Remote:
    def __init__(self):
        self.starts = []

    def submit(self, job, directory):
        assert all((directory / "source" / item["stored_name"]).is_file() for item in job["files"])
        self.starts.append(job["id"])
        return {"status": "running", "stage": "training"}

    def inspect(self, job_id):
        assert job_id in self.starts
        return {"status": "completed", "stage": "completed", "artifact": {"relative_path": "projects/test/final.ply", "size": len(PLY), "sha256": hashlib.sha256(PLY).hexdigest(), "kind": "point_cloud", "point_count": 1}}

    def download(self, job_id, artifact, path):
        assert job_id in self.starts
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PLY)


@pytest.mark.asyncio
@pytest.mark.parametrize("input_type", ["images", "video"])
async def test_new_point_model_import_rebuild_and_same_material_new_run_keep_history(tmp_path, input_type):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(point_metadata.create_all)
        await connection.run_sync(job_metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    remote = Remote()
    service = ReconstructionService(ReconstructionConfig(local_root=tmp_path / "assets"), JobStore(sessions), remote)
    app = FastAPI()
    for router in [custom_map_points.router, map_models.router, reconstructions.router]:
        app.include_router(router)
    app.dependency_overrides[custom_map_points.get_current_user_from_request] = lambda: SimpleNamespace(id="admin", system_role="admin")
    app.dependency_overrides[custom_map_points.get_store] = lambda: MapPointsStore(sessions)
    app.dependency_overrides[reconstructions.get_service] = lambda: service
    app.dependency_overrides[map_models.map_points.get_versioned_catalog_source] = lambda: None
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            point = (await client.post("/api/map/custom-points", json={"name": "新建点位", "lon": 120.5, "lat": 31.2, "request_id": "point"})).json()
            imported = await client.post("/api/map/model-assets", data={"title": "原有模型", "point_id": point["id"]}, files={"file": ("color.ply", PLY)})
            assert imported.status_code == 201, imported.text
            original = imported.json()
            media = [("files", ("a.jpg", b"photo-a")), ("files", ("b.jpg", b"photo-b"))] if input_type == "images" else [("files", ("orbit.mp4", b"0000ftypmp42-orbit"))]
            created_ids = []
            for request_id in ["first-reconstruction", "rebuild-same-material"]:
                form = {"title": "同一点位重建", "point_id": point["id"], "point_name": point["name"], "quality": "fast", "request_id": request_id}
                response = await client.post("/api/reconstructions", data=form, files=media)
                assert response.status_code == 202, response.text
                job_id = response.json()["id"]
                created_ids.append(job_id)
                await asyncio.gather(*list(service.tasks.values()))
                completed = await client.get(f"/api/reconstructions/{job_id}")
                assert completed.json()["status"] == "completed"
                assert completed.json()["input_type"] == input_type
                retry = await client.post("/api/reconstructions", data=form, files=media)
                assert retry.json()["id"] == job_id
                assets = (await client.get("/api/map/model-assets")).json()
                asset = next(item for item in assets if item["id"] == job_id)
                assert (asset["point_id"], asset["entity_id"], asset["source"]) == (point["id"], point["entity_id"], "reconstruction")
                assert (await client.get(asset["preview_url"])).content == PLY
                assert (await client.get(original["preview_url"])).content == PLY
            assert created_ids[0] != created_ids[1]
            assert remote.starts == created_ids
            assert len((await client.get("/api/map/model-assets")).json()) == 3
            assert len((await client.get("/api/reconstructions", params={"point_id": point["id"]})).json()) == 2
            restored = ReconstructionService(service.config, JobStore(sessions), remote)
            assert (await restored.refresh(created_ids[0]))["status"] == "completed"
            await restored.close()
    finally:
        await service.close()
        await engine.dispose()
