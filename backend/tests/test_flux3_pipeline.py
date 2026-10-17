import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway.reconstructions import flux_pipeline, runner
from app.gateway.reconstructions.config import ReconstructionConfig
from app.gateway.reconstructions.service import ReconstructionService
from app.gateway.reconstructions.store import JobStore, metadata
from app.gateway.routers import reconstructions


def test_reference_workflow_preserves_resolution_and_uses_only_prompt_editing():
    graph = flux_pipeline.build_workflow("xingxi/job/00000.png", "White background", 42, "xingxi/job/00000")
    assert graph["17"]["inputs"]["resolution"] == "keep resolution"
    assert graph["17"]["inputs"]["images.image0"] == ["11", 0]
    assert graph["4"]["inputs"]["text"] == "White background"
    assert graph["7"]["inputs"]["steps"] == 16 and graph["7"]["inputs"]["seed"] == 42
    assert not any("mask" in node["class_type"].lower() or "sam" in node["class_type"].lower() and node["class_type"] != "KSampler" for node in graph.values())


def test_comfy_result_is_scoped_to_output_and_selected_prompt(tmp_path):
    folder = tmp_path / "output"
    folder.mkdir()
    (folder / "frame.png").write_bytes(b"png")
    assert flux_pipeline.output_file(folder, {"filename": "frame.png", "subfolder": "", "type": "output"}) == folder / "frame.png"
    for row in [{"filename": "../outside.png"}, {"filename": "frame.png", "subfolder": ".."}, {"filename": "frame.png", "type": "input"}]:
        with pytest.raises(ValueError):
            flux_pipeline.output_file(folder, row)


def test_preprocessing_keeps_all_inputs_even_if_colmap_registers_only_subset(tmp_path):
    originals, calibrated = tmp_path / "originals", tmp_path / "undistorted"
    originals.mkdir()
    calibrated.mkdir()
    for name in ["00000.png", "00001.png", "00002.png"]:
        (originals / name).touch()
    (calibrated / "00001.png").touch()
    views = flux_pipeline.reference_views(originals, calibrated)
    assert len(views) == 3
    assert views[1] == calibrated / "00001.png"
    assert views[0] == originals / "00000.png"


def test_fused_result_manifest_is_not_fabricated_native_project(tmp_path):
    path = tmp_path / "projects/flux3/final.ply"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n0 0 0 255 0 0\n")
    manifest = {"schema_version": 1, "pipeline_profile": "flux3_rgb_subject_v1", "status": "completed", "output": {"finalPly": str(path)}}
    (tmp_path / "pipeline_result.json").write_text(json.dumps(manifest))
    assert runner.validate_result(tmp_path)["point_count"] == 1
    manifest["status"] = "running"
    (tmp_path / "pipeline_result.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        runner.validate_result(tmp_path)


@pytest.mark.parametrize("pending", [True, False])
def test_flux_cancellation_is_scoped_and_never_interrupts_other_jobs(monkeypatch, pending):
    calls = []

    class FakeComfy(flux_pipeline.Comfy):
        def __init__(self):
            self.polls = 0

        def request(self, path, data=None):
            calls.append((path, data))
            if path == "/history/owned":
                self.polls += 1
                return {} if self.polls == 1 else {"owned": {"status": {"status_str": "success"}}}
            if path == "/queue" and data is None:
                return {"queue_pending": [[1, "owned"], [2, "unrelated"]] if pending else [], "queue_running": [[0, "owned"]]}
            return {}

    monkeypatch.setattr(flux_pipeline.time, "sleep", lambda _: None)
    with pytest.raises(flux_pipeline.Cancelled):
        FakeComfy().wait("owned", lambda: True)
    assert all(path != "/interrupt" for path, _ in calls)
    deletions = [data for path, data in calls if path == "/queue" and data]
    assert deletions == ([{"delete": ["owned"]}] if pending else [])


def test_fused_supervisor_waits_for_adapter_cancellation_without_global_signal(tmp_path, monkeypatch):
    config = {"executable": "splatstudio", "quality": "fast", "input": ".", "preprocessing": "flux3", "flux3": {"python": "python3"}}
    (tmp_path / "config.json").write_text(json.dumps(config))
    killed = []

    class Process:
        pid = 123
        polls = 0

        def poll(self):
            self.polls += 1
            (tmp_path / "cancel.request").touch()
            return None if self.polls == 1 else 130

        def wait(self, **kwargs):
            return 130

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    monkeypatch.setattr(runner.os, "killpg", lambda *args: killed.append(args), raising=False)
    runner.run(tmp_path)
    assert runner.read_json(tmp_path / "status.json")["status"] == "cancelled" and not killed


@pytest.mark.asyncio
async def test_flux_upload_snapshot_idempotency_and_unavailable_service(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)

    class Remote:
        def __init__(self):
            self.jobs = []

        def submit(self, job, directory):
            self.jobs.append(job)
            return {"status": "running", "stage": "preprocessing", "preprocess_progress": {"completed": 0, "total": 2}}

    remote = Remote()
    service = ReconstructionService(ReconstructionConfig(local_root=tmp_path, flux3_root="/deployed/flux3"), JobStore(async_sessionmaker(engine, expire_on_commit=False)), remote)
    app = FastAPI()
    app.include_router(reconstructions.router)
    app.dependency_overrides[reconstructions.get_service] = lambda: service
    app.dependency_overrides[reconstructions.get_current_user_from_request] = lambda: SimpleNamespace(id="admin", system_role="admin")
    form = {"title": "Bridge", "request_id": "same-flux", "preprocessing": "flux3", "preprocess_prompt": "Clean white background"}
    files = [("files", ("a.png", b"original-a", "image/png")), ("files", ("b.png", b"original-b", "image/png"))]
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            capabilities = (await client.get("/api/reconstructions/capabilities")).json()
            assert capabilities["flux3_enabled"] is True
            first = await client.post("/api/reconstructions", data=form, files=files)
            assert first.status_code == 202
            await asyncio.gather(*list(service.tasks.values()))
            jid = first.json()["id"]
            stored = await service.get(jid)
            assert stored["preprocessing"] == "flux3" and stored["preprocess_prompt"] == form["preprocess_prompt"]
            second = await client.post("/api/reconstructions", data=form, files=files)
            assert second.json()["id"] == jid and len(remote.jobs) == 1
            changed = await client.post("/api/reconstructions", data={**form, "preprocess_prompt": "Different edit"}, files=files)
            assert changed.status_code == 409
            service.config = replace(service.config, flux3_root="")
            assert (await client.post("/api/reconstructions", data={**form, "request_id": "disabled"}, files=files)).status_code == 503
    finally:
        await service.close()
        await engine.dispose()


def test_completed_flux_progress_reaches_total_without_mutating_stored_history():
    stored = {"status": "completed", "files": [], "preprocessing": "flux3", "preprocess_progress": {"completed": 15, "total": 16}}
    service = ReconstructionService(None, None, None)
    assert service.public(stored)["preprocess_progress"] == {"completed": 16, "total": 16}
    assert stored["preprocess_progress"]["completed"] == 15


def test_cancel_waits_if_owned_prompt_starts_while_pending_delete_is_sent(monkeypatch):
    class RacingComfy(flux_pipeline.Comfy):
        def __init__(self):
            self.history_reads = 0
            self.delete_sent = False

        def request(self, path, data=None):
            if path == "/history/owned":
                self.history_reads += 1
                return {} if self.history_reads == 1 else {"owned": {"status": {"status_str": "success"}}}
            if path == "/queue" and data:
                assert data == {"delete": ["owned"]}
                self.delete_sent = True
                return {}
            return {"queue_pending": [] if self.delete_sent else [[1, "owned"]], "queue_running": [[1, "owned"]] if self.delete_sent else []}

    monkeypatch.setattr(flux_pipeline.time, "sleep", lambda _: None)
    client = RacingComfy()
    with pytest.raises(flux_pipeline.Cancelled):
        client.wait("owned", lambda: True)
    assert client.history_reads == 2
