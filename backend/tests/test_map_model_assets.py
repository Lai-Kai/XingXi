from __future__ import annotations

import json
import struct
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway.reconstructions.config import ReconstructionConfig
from app.gateway.reconstructions.service import ReconstructionService
from app.gateway.reconstructions.store import JobStore, metadata
from app.gateway.routers import map_models, reconstructions


def ply():
    return b"ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" + struct.pack(
        "<fffBBB", 0, 0, 0, 255, 128, 0
    )


def glb(external=False):
    value = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": []}]}
    if external:
        value["buffers"] = [{"uri": "https://example.test/private.bin", "byteLength": 3}]
    data = json.dumps(value).encode()
    data += b" " * (-len(data) % 4)
    return struct.pack("<4sIIII", b"glTF", 2, len(data) + 20, len(data), 0x4E4F534A) + data


class Remote:
    def submit(self, *args):
        raise AssertionError("Import must not start SSH or training")

    def download(self, *args):
        raise AssertionError("Imported files must be read locally")


@pytest_asyncio.fixture
async def setup(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    service = ReconstructionService(ReconstructionConfig(local_root=tmp_path), JobStore(async_sessionmaker(engine, expire_on_commit=False)), Remote())
    app = FastAPI()
    app.include_router(map_models.router)
    app.include_router(reconstructions.router)
    user = SimpleNamespace(id="admin", system_role="admin")
    app.dependency_overrides[map_models.get_current_user_from_request] = lambda: user
    app.dependency_overrides[map_models.get_service] = lambda: service
    app.dependency_overrides[map_models.get_model_points] = lambda: {"pt-known": SimpleNamespace(id="pt-known", entity_id="entity-known", name="已有古桥")}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, service, user
    await service.close()
    await engine.dispose()


async def upload(client, data=None, name="彩色模型.ply", body=None):
    return await client.post("/api/map/model-assets", data={"title": "古桥新模型", "point_id": "pt-known", **(data or {})}, files={"file": (name, ply() if body is None else body, "application/octet-stream")})


@pytest.mark.asyncio
@pytest.mark.parametrize("extension,body,kind", [("ply", ply(), "point_cloud"), ("glb", glb(), "mesh")])
async def test_import_persists_exact_point_binding_and_reads_after_service_restart(setup, extension, body, kind):
    client, service, _ = setup
    response = await upload(client, name=f"model.{extension}", body=body)
    assert response.status_code == 201, response.text
    asset = response.json()
    assert (asset["point_id"], asset["entity_id"], asset["kind"], asset["format"]) == ("pt-known", "entity-known", kind, extension)
    assert asset["size_bytes"] == len(body)
    assert "relative_path" not in str(asset) and "stored_name" not in str(asset)
    assert len(await service.store.list("pt-known")) == 1
    restored = ReconstructionService(service.config, service.store, Remote())
    assert (await restored.get(asset["id"]))["status"] == "completed"
    assert (await client.get("/api/map/model-assets", params={"point_id": "pt-known"})).json() == [asset]
    result = await client.get(asset["preview_url"])
    assert result.content == body
    assert result.headers["cache-control"] == "private, no-store"
    assert "inline" in result.headers["content-disposition"]
    assert "attachment" in (await client.get(asset["download_url"])).headers["content-disposition"]
    ranged = await client.get(asset["preview_url"], headers={"Range": "bytes=0-3"})
    assert ranged.status_code == 206 and ranged.content == body[:4]
    assert (await client.get("/api/reconstructions")).json() == []


@pytest.mark.asyncio
async def test_only_admin_can_import_but_signed_in_reader_can_preview(setup):
    client, _, user = setup
    asset = (await upload(client)).json()
    user.system_role = "user"
    assert (await upload(client)).status_code == 403
    assert len((await client.get("/api/map/model-assets")).json()) == 1
    assert (await client.get(asset["preview_url"])).content == ply()
    assert (await client.get("/api/reconstructions")).status_code == 403


@pytest.mark.asyncio
async def test_import_retries_are_idempotent_and_changed_files_conflict_without_litter(setup):
    client, service, _ = setup
    first = await upload(client, data={"request_id": "same"})
    again = await upload(client, data={"request_id": "same"})
    assert first.json()["id"] == again.json()["id"]
    changed = await upload(client, data={"request_id": "same", "title": "另一个模型"})
    assert changed.status_code == 409
    assert len([p for p in service.config.local_root.iterdir() if p.is_dir()]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("name,body", [("model.ply", b"invalid"), ("model.glb", b"glTFbad"), ("../model.ply", ply()), ("image.jpg", ply()), ("external.glb", glb(external=True))])
async def test_rejects_invalid_files_and_does_not_leave_completed_records(setup, name, body):
    client, service, _ = setup
    response = await upload(client, name=name, body=body)
    assert response.status_code == 400
    assert await service.store.list() == []
    assert list(service.config.local_root.glob("*/model.*")) == []


@pytest.mark.asyncio
async def test_unknown_point_actual_byte_limit_and_multiple_file_rejection(setup):
    client, service, _ = setup
    assert (await upload(client, data={"point_id": "made-up"})).status_code == 404
    assert (await upload(client, data={"title": "   "})).status_code == 422
    service.config = replace(service.config, max_bytes=10)
    assert (await upload(client)).status_code == 413
    service.config = replace(service.config, max_bytes=2 * 1024**3)
    response = await client.post("/api/map/model-assets", data={"point_id": "pt-known", "title": "multiple"}, files=[("file", ("a.ply", ply())), ("file", ("b.ply", ply()))])
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_completed_reconstruction_is_available_as_asset_without_exposing_management(setup):
    client, service, user = setup
    job_id = "71ca3eba-2a96-4140-a558-ea8130863cc5"
    directory = service.config.local_root / job_id
    directory.mkdir()
    (directory / "final.ply").write_bytes(ply())
    record = {
        "id": job_id,
        "owner_id": "admin",
        "point_id": "pt-known",
        "point_name": "旧名",
        "request_id": "job",
        "created_at": "2026-10-17T00:00:00Z",
        "fingerprint": "job",
        "input_type": "video",
        "quality": "high",
        "status": "completed",
        "title": "已有重建",
        "log": "private SSH log",
        "files": [],
        "artifact": {"size": len(ply()), "sha256": "a" * 64, "splat_count": 1},
    }
    await service.store.create(record)
    user.system_role = "user"
    assets = (await client.get("/api/map/model-assets")).json()
    assert len(assets) == 1 and assets[0]["source"] == "reconstruction"
    assert "private SSH log" not in str(assets)
    assert (await client.get(assets[0]["preview_url"])).content == ply()
    await service.store.create({**record, "id": "unknown-point", "point_id": "not-in-catalog", "request_id": "other"})
    assert len((await client.get("/api/map/model-assets")).json()) == 1


@pytest.mark.asyncio
async def test_file_storage_work_is_off_event_loop(setup, monkeypatch):
    import threading

    from app.gateway.reconstructions import model_files

    client, _, _ = setup
    original = model_files.copy_model
    main_thread = threading.get_ident()

    def checked(*args, **kwargs):
        assert threading.get_ident() != main_thread
        return original(*args, **kwargs)

    monkeypatch.setattr(model_files, "copy_model", checked)
    assert (await upload(client)).status_code == 201


@pytest.mark.asyncio
async def test_multi_chunk_ply_upload_preserves_spooled_file_bytes_and_ranges(setup):
    client, _, _ = setup
    header, vertex = ply().split(b"end_header\n")
    payload = header.replace(b"element vertex 1", b"element vertex 180000") + b"end_header\n" + vertex * 180000
    assert len(payload) > 2 * 1024**2
    response = await upload(client, body=payload)
    assert response.status_code == 201
    asset = response.json()
    assert asset["point_count"] == 180000 and asset["size_bytes"] == len(payload)
    assert (await client.get(asset["preview_url"])).content == payload
    ranged = await client.get(asset["preview_url"], headers={"Range": "bytes=1048574-1048583"})
    assert ranged.status_code == 206 and ranged.content == payload[1048574:1048584]
