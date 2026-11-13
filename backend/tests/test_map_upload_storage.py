"""Bounded map uploads are admitted before FastAPI can spool multipart files."""

from __future__ import annotations

import asyncio
import errno
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Form
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.gateway.reconstructions import storage
from app.gateway.reconstructions.config import ReconstructionConfig
from app.gateway.upload_storage_middleware import MapUploadStorageMiddleware


def probe(monkeypatch, devices, free):
    monkeypatch.setattr(storage, "_filesystem", lambda path: (devices[str(path)], path))
    calls = []

    def disk_usage(path):
        calls.append(path)
        return SimpleNamespace(free=free[devices[str(path)]])

    monkeypatch.setattr(storage.shutil, "disk_usage", disk_usage)
    return calls


def test_shared_filesystem_sums_both_live_copies_and_checks_once(monkeypatch):
    calls = probe(monkeypatch, {"temp": 1, "models": 1}, {1: 249})
    budget = storage.StorageBudget(min_free_bytes=50)
    with pytest.raises(storage.HTTPException) as error:
        budget.reserve(Path("temp"), Path("models"), 100, 100)
    assert error.value.status_code == 507
    assert len(calls) == 1
    assert budget.reserved == {}


def test_different_filesystems_are_checked_independently(monkeypatch):
    probe(monkeypatch, {"temp": 1, "models": 2}, {1: 150, 2: 149})
    budget = storage.StorageBudget(min_free_bytes=50)
    with pytest.raises(storage.HTTPException) as error:
        budget.reserve(Path("temp"), Path("models"), 100, 100)
    assert error.value.status_code == 507
    assert budget.reserved == {}


def test_concurrent_reservations_are_released_without_double_counting(monkeypatch):
    probe(monkeypatch, {"temp": 1, "models": 1}, {1: 350})
    budget = storage.StorageBudget(min_free_bytes=50)
    first = budget.reserve(Path("temp"), Path("models"), 100, 100)
    with pytest.raises(storage.HTTPException):
        budget.reserve(Path("temp"), Path("models"), 100, 100)
    first.release()
    first.release()
    second = budget.reserve(Path("temp"), Path("models"), 100, 100)
    second.release()
    assert budget.reserved == {}


def make_app(tmp_path, monkeypatch, *, role="admin", space=10**12):
    app = FastAPI()
    config = ReconstructionConfig(local_root=tmp_path / "saved")
    budget = storage.StorageBudget(min_free_bytes=0)
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda path: SimpleNamespace(free=space))
    app.add_middleware(MapUploadStorageMiddleware, config_factory=lambda: config, budget=budget, temp_root=tmp_path)

    @app.middleware("http")
    async def auth(request, call_next):
        if role:
            request.state.user = SimpleNamespace(system_role=role)
        return await call_next(request)

    @app.post("/api/reconstructions")
    @app.post("/api/map/model-assets")
    async def create(title: str = Form()):
        return {"title": title}

    return app, budget, config


@pytest.mark.asyncio
async def test_low_disk_is_rejected_before_multipart_parser_reads_any_body(tmp_path, monkeypatch):
    app, budget, _ = make_app(tmp_path, monkeypatch, space=0)
    reads = []

    async def body():
        reads.append(True)
        yield b"not actually multipart"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/reconstructions", content=body(), headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert response.status_code == 507
    assert "空间不足" in response.json()["detail"]
    assert reads == []
    assert budget.reserved == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "expected"), [(None, 401), ("user", 403)])
async def test_authorization_precedes_space_probe(tmp_path, monkeypatch, role, expected):
    app, _, _ = make_app(tmp_path, monkeypatch, role=role, space=0)

    def forbidden(*args):
        raise AssertionError("Unauthorized requests must not probe storage")

    monkeypatch.setattr(storage, "_filesystem", forbidden)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/reconstructions", content=b"x")
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "limit"), [("/api/reconstructions", 2 * 1024**3), ("/api/map/model-assets", 256 * 1024**2)])
async def test_existing_limits_allow_multipart_overhead_but_reject_oversize_before_read(tmp_path, monkeypatch, path, limit):
    app, _, _ = make_app(tmp_path, monkeypatch)
    reads = []

    async def body():
        reads.append(True)
        yield b"x"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, content=body(), headers={"Content-Length": str(limit + storage.MULTIPART_OVERHEAD_BYTES + 1)})
    assert response.status_code == 413
    assert reads == []


@pytest.mark.asyncio
async def test_success_releases_budget_and_offloads_filesystem_probe(tmp_path, monkeypatch):
    app, budget, _ = make_app(tmp_path, monkeypatch)
    original = storage._filesystem
    thread_ids = []

    def checked(path):
        thread_ids.append(threading.get_ident())
        return original(path)

    monkeypatch.setattr(storage, "_filesystem", checked)
    event_loop_thread = threading.get_ident()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/reconstructions", data={"title": "桥"}, files={"files": ("a.jpg", b"image")})
    assert response.status_code == 200
    assert response.json() == {"title": "桥"}
    assert thread_ids and all(item != event_loop_thread for item in thread_ids)
    assert budget.reserved == {}


@pytest.mark.asyncio
async def test_lying_content_length_cannot_exceed_reserved_budget(tmp_path, monkeypatch):
    app, budget, _ = make_app(tmp_path, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/reconstructions", content=b"title=too-long", headers={"Content-Length": "1", "Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 413
    assert budget.reserved == {}


@pytest.mark.asyncio
async def test_unrelated_routes_do_not_trigger_storage_probe(tmp_path, monkeypatch):
    app, _, _ = make_app(tmp_path, monkeypatch, space=0)

    @app.post("/api/reconstructions/job/cancel")
    async def cancel():
        return {"cancelled": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/reconstructions/job/cancel")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_fastapi_form_parser_wraps_spool_enospc_but_preserves_its_cause(tmp_path, monkeypatch):
    from starlette.requests import Request

    app, budget, _ = make_app(tmp_path, monkeypatch)
    captured = []

    @app.exception_handler(StarletteHTTPException)
    async def handle_spool_error(request, error):
        from app.gateway.errors import gateway_error_response

        captured.append(error)
        if storage.is_storage_exhaustion(error):
            failure = storage.insufficient_storage()
            return gateway_error_response(failure.status_code, failure.detail)
        return gateway_error_response(error.status_code, error.detail)

    async def no_space(*args, **kwargs):
        raise OSError(errno.ENOSPC, "no space left on device")

    monkeypatch.setattr(Request, "_get_form", no_space)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/reconstructions", data={"title": "桥"}, files={"files": ("a.jpg", b"image")})
    assert response.status_code == 507
    assert captured[0].status_code == 400
    assert storage.is_storage_exhaustion(captured[0])
    assert budget.reserved == {}


@pytest.mark.asyncio
async def test_cancellation_while_thread_is_admitting_releases_eventual_reservation(tmp_path, monkeypatch):
    app, budget, _ = make_app(tmp_path, monkeypatch)
    started, finish, reserved = threading.Event(), threading.Event(), threading.Event()
    original = budget.reserve

    def slow(*args):
        started.set()
        finish.wait(5)
        result = original(*args)
        reserved.set()
        return result

    monkeypatch.setattr(budget, "reserve", slow)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        task = asyncio.create_task(client.post("/api/reconstructions", data={"title": "桥"}))
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        finish.set()
        assert await asyncio.to_thread(reserved.wait, 2)
        # The worker and its done callback must complete, not just the HTTP task.
        for _ in range(100):
            await asyncio.sleep(0.01)
            if not budget.reserved:
                break
    assert budget.reserved == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("length", ["-1", "not-a-number", "９９", "9" * 5000])
async def test_invalid_content_length_never_reaches_parser(tmp_path, monkeypatch, length):
    app, budget, _ = make_app(tmp_path, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        headers = [(b"Content-Length", length.encode("utf-8"))]
        response = await client.post("/api/reconstructions", content=b"x", headers=headers)
    assert response.status_code in {400, 413}
    assert budget.reserved == {}
