from __future__ import annotations

import asyncio
import json
import struct
import threading
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway.map_model_points import get_model_points
from app.gateway.reconstructions import runner
from app.gateway.reconstructions.config import ReconstructionConfig
from app.gateway.reconstructions.service import ReconstructionService
from app.gateway.reconstructions.store import JobStore, metadata
from app.gateway.routers import reconstructions


class Remote:
    def __init__(self):
        self.starts = []
        self.state = {"status": "running", "stage": "Reconstructing", "log": "COLMAP"}

    def submit(self, job, directory):
        self.starts.append(job["id"])
        return dict(self.state)

    def inspect(self, job_id):
        return dict(self.state)

    def cancel(self, job_id):
        self.state = {"status": "cancelled", "stage": "cancelled", "log": ""}
        return dict(self.state)


@pytest_asyncio.fixture
async def fixture(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    config = ReconstructionConfig(local_root=tmp_path, ssh_config=tmp_path / "ssh.json")
    remote = Remote()
    service = ReconstructionService(config, JobStore(async_sessionmaker(engine, expire_on_commit=False)), remote)
    app = FastAPI()
    app.include_router(reconstructions.router)
    app.dependency_overrides[reconstructions.get_service] = lambda: service
    app.dependency_overrides[get_model_points] = lambda: {
        "pt-bridge": SimpleNamespace(id="pt-bridge", entity_id="entity-bridge", name="古桥"),
        "point": SimpleNamespace(id="point", entity_id="entity", name="古桥"),
    }
    app.dependency_overrides[reconstructions.get_current_user_from_request] = lambda: SimpleNamespace(id="admin", system_role="admin")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, service, remote, app
    await service.close()
    await engine.dispose()


def files():
    return [("files", ("a.jpg", b"\xff\xd8\xffexample-a", "image/jpeg")), ("files", ("b.png", b"\x89PNG\r\n\x1a\nexample-b", "image/png"))]


@pytest.mark.asyncio
async def test_upload_starts_immediately_and_retries_do_not_duplicate(fixture):
    client, service, remote, _ = fixture
    form = {"title": "古桥", "point_id": "pt-bridge", "point_name": "古桥", "quality": "fast", "request_id": "same-request"}
    response = await client.post("/api/reconstructions", data=form, files=files())
    assert response.status_code == 202
    job = response.json()
    assert job["status"] in {"transferring", "running"}
    await asyncio.gather(*list(service.tasks.values()))
    again = await client.post("/api/reconstructions", data=form, files=files())
    assert again.json()["id"] == job["id"]
    assert remote.starts == [job["id"]]
    assert (await client.get("/api/reconstructions", params={"point_id": "pt-bridge"})).json()[0]["id"] == job["id"]
    assert "ssh" not in str(job).lower()


@pytest.mark.asyncio
async def test_state_survives_service_restart_and_remote_failure_is_visible(fixture):
    client, service, remote, _ = fixture
    response = await client.post("/api/reconstructions", data={"title": "测试", "quality": "balanced", "request_id": "restart"}, files=files())
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))
    restored = ReconstructionService(service.config, service.store, remote)
    remote.state = {"status": "failed", "stage": "failed", "error": "重建失败", "log": "COLMAP failed"}
    result = await restored.refresh(job_id)
    assert result["status"] == "failed"
    assert result["error"] == "重建失败"
    assert result["log"] == "COLMAP failed"
    assert len(remote.starts) == 1
    await restored.close()


@pytest.mark.asyncio
async def test_reject_mixed_media_bad_quality_traversal_and_public_user(fixture):
    client, _, remote, app = fixture
    for payload in [
        [("files", ("input.mp4", b"0000ftypmp42", "video/mp4")), *files()],
        [("files", ("../a.jpg", b"fake", "image/jpeg"))],
    ]:
        assert (await client.post("/api/reconstructions", data={"title": "测试", "quality": "fast"}, files=payload)).status_code == 400
    assert (await client.post("/api/reconstructions", data={"title": "测试", "quality": "bad"}, files=files())).status_code == 422
    app.dependency_overrides[reconstructions.get_current_user_from_request] = lambda: SimpleNamespace(id="reader", system_role="user")
    assert (await client.get("/api/reconstructions")).status_code == 403
    assert (await client.post("/api/reconstructions", data={"title": "测试"}, files=files())).status_code == 403
    assert remote.starts == []


@pytest.mark.asyncio
async def test_cancel_is_scoped_to_the_exact_job(fixture):
    client, service, remote, _ = fixture
    response = await client.post("/api/reconstructions", data={"title": "测试", "quality": "high"}, files=files())
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))
    assert (await client.post(f"/api/reconstructions/{job_id}/cancel")).json()["status"] == "cancelled"
    assert remote.starts == [job_id]
    assert (await client.get("/api/reconstructions/not-an-id")).status_code == 404


@pytest.mark.asyncio
async def test_actual_byte_limit_and_idempotency_conflict(fixture):
    client, service, remote, _ = fixture
    service.config = replace(service.config, max_bytes=10)
    assert (await client.post("/api/reconstructions", data={"title": "大小检查"}, files=files())).status_code == 413
    assert remote.starts == []
    service.config = replace(service.config, max_bytes=4096)
    response = await client.post("/api/reconstructions", data={"title": "首次", "request_id": "repeat"}, files=files())
    assert response.status_code == 202
    await asyncio.gather(*list(service.tasks.values()))
    conflict = await client.post("/api/reconstructions", data={"title": "不同任务", "request_id": "repeat"}, files=files())
    assert conflict.status_code == 409
    assert len(remote.starts) == 1


@pytest.mark.asyncio
async def test_connection_loss_does_not_report_training_failure(fixture):
    client, service, remote, _ = fixture
    response = await client.post("/api/reconstructions", data={"title": "视频"}, files=[("files", ("环拍.mp4", b"0000ftypmp42", "video/mp4"))])
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))

    def disconnected(_):
        raise OSError("connection reset")

    remote.inspect = disconnected
    job = (await client.get(f"/api/reconstructions/{job_id}")).json()
    assert job["status"] == "running" and job["connection_error"]
    assert "connection reset" not in str(job)
    assert (await client.get(f"/api/reconstructions/{job_id}/artifact/final.ply")).status_code == 409


@pytest.mark.asyncio
async def test_service_initialization_is_shared_and_resolves_paths_off_event_loop(fixture, monkeypatch):
    _, service, _, app = fixture
    main_thread = threading.get_ident()

    def configure():
        assert threading.get_ident() != main_thread
        return service.config

    monkeypatch.setattr(reconstructions, "ReconstructionConfig", configure)
    monkeypatch.setattr(reconstructions, "get_session_factory", lambda: service.store.sessions)
    request = Request({"type": "http", "app": app})
    instances = await asyncio.gather(*(reconstructions.get_service(request) for _ in range(5)))
    assert all(instance is instances[0] for instance in instances)


def make_result(root, *, valid=True, target=None):
    project = root / "projects" / "generated"
    project.mkdir(parents=True)
    ply = project / "final.ply"
    attributes = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"] if valid else ["x", "y", "z"]
    header = "ply\nformat binary_little_endian 1.0\nelement vertex 1\n" + "".join(f"property float {name}\n" for name in attributes) + "end_header\n"
    ply.write_bytes(header.encode() + struct.pack("<" + "f" * len(attributes), *([1.0] * len(attributes))))
    (project / "project.json").write_text(json.dumps({"status": "completed", "output": {"finalPly": str(target or ply)}}))
    return ply


def test_result_requires_real_gaussian_properties_and_job_scoped_path(tmp_path):
    good = tmp_path / "good"
    make_result(good)
    result = runner.validate_result(good)
    assert result["splat_count"] == 1 and len(result["sha256"]) == 64
    bad = tmp_path / "bad"
    make_result(bad, valid=False)
    with pytest.raises(ValueError, match="Gaussian"):
        runner.validate_result(bad)
    escaped = tmp_path / "escaped"
    make_result(escaped, target=good / "projects/generated/final.ply")
    with pytest.raises(ValueError):
        runner.validate_result(escaped)


@pytest.mark.parametrize("encoding", ["ascii", "binary_little_endian", "binary_big_endian"])
@pytest.mark.parametrize("colors", [("red", "green", "blue"), ("r", "g", "b"), ("diffuse_red", "diffuse_green", "diffuse_blue")])
def test_result_accepts_rgb_ply_without_gaussian_attributes(tmp_path, encoding, colors):
    path = make_result(tmp_path)
    header = f"ply\r\nformat {encoding} 1.0\r\nelement vertex 2\r\n"
    header += "".join(f"property float {name}\r\n" for name in ("x", "y", "z"))
    header += "".join(f"property uchar {name}\r\n" for name in (*colors, "alpha")) + "end_header\r\n"
    body = b"0 0 0 255 0 0 255\n1 1 1 0 128 255 128\n" if encoding == "ascii" else struct.pack(("<" if encoding == "binary_little_endian" else ">") + "fffBBBBfffBBBB", 0, 0, 0, 255, 0, 0, 255, 1, 1, 1, 0, 128, 255, 128)
    path.write_bytes(header.encode() + body)
    result = runner.validate_result(tmp_path)
    assert result["kind"] == "point_cloud"
    assert result["point_count"] == 2
    assert "splat_count" not in result
    assert result["size"] == path.stat().st_size


def test_face_colors_cannot_disguise_uncolored_vertices(tmp_path):
    path = make_result(tmp_path, valid=False)
    header, data = path.read_bytes().split(b"end_header\n")
    path.write_bytes(header + b"element face 1\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" + data)
    with pytest.raises(ValueError, match="Gaussian|RGB"):
        runner.validate_result(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("artifact", [{"kind": "point_cloud", "point_count": 2}, {"kind": "gaussian", "splat_count": 2}, {"splat_count": 2}])
async def test_ply_artifact_metadata_survives_refresh_and_download(fixture, artifact):
    client, service, remote, _ = fixture
    response = await client.post("/api/reconstructions", data={"title": "彩色模型"}, files=files())
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))
    metadata = {"size": 30, "sha256": "a" * 64, **artifact, "relative_path": "projects/generated/final.ply"}
    remote.state = {"status": "completed", "stage": "completed", "artifact": metadata}
    result = (await client.get(f"/api/reconstructions/{job_id}")).json()
    assert result["artifact"] == {key: value for key, value in metadata.items() if key != "relative_path"}
    (service.config.local_root / job_id / "final.ply").write_bytes(b"cached-ply")
    assert (await client.get(result["artifact_url"])).content == b"cached-ply"
    assert (await client.get("/api/reconstructions")).json()[0]["artifact"] == result["artifact"]


def test_remote_supervisor_claim_and_exact_process_group_cancel(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(json.dumps({"executable": "splatstudio", "quality": "fast", "input": "input.mp4"}))
    started, killed = [], []

    class Process:
        pid = 144

        def poll(self):
            (tmp_path / "cancel.request").touch()
            return None

        def wait(self, **kwargs):
            return -15

    def start(arguments, **kwargs):
        started.append(arguments)
        return Process()

    monkeypatch.setattr(runner.subprocess, "Popen", start)
    monkeypatch.setattr(runner.os, "killpg", lambda pid, sig: killed.append(pid), raising=False)
    runner.run(tmp_path)
    runner.run(tmp_path)
    assert len(started) == 1 and killed == [144]
    assert runner.read_json(tmp_path / "status.json")["status"] == "cancelled"
