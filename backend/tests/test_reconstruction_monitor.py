from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import insert
from test_reconstructions import files
from test_reconstructions import fixture as fixture

from app.gateway.reconstructions.service import ReconstructionService
from app.gateway.reconstructions.store import jobs
from app.gateway.routers.map_models import descriptor


@pytest.mark.asyncio
async def test_monitor_registers_result_without_any_detail_get(fixture):
    client, service, remote, _ = fixture
    response = await client.post("/api/reconstructions", data={"title": "无人值守", "point_id": "point"}, files=files())
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))
    remote.state = {"status": "completed", "stage": "completed", "artifact": {"size": 100, "sha256": "a" * 64, "kind": "point_cloud", "point_count": 2}}
    service.start_monitor(interval=0.01)
    async with asyncio.timeout(2):
        while (await service.get(job_id))["status"] != "completed":
            await asyncio.sleep(0.01)
    point = SimpleNamespace(id="point", entity_id="entity")
    assert descriptor(await service.get(job_id), {"point": point}) is not None
    assert len(remote.starts) == 1


@pytest.mark.asyncio
async def test_restart_only_inspects_transferring_never_resubmits(fixture):
    client, service, remote, _ = fixture

    def broken_submit(*args):
        raise OSError("lost SSH acknowledgement")

    remote.submit = broken_submit
    response = await client.post("/api/reconstructions", data={"title": "回执丢失"}, files=files())
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))
    restored = ReconstructionService(service.config, service.store, remote)
    remote.state = {"status": "running", "stage": "training"}
    restored.start_monitor(interval=0.01)
    try:
        async with asyncio.timeout(2):
            while (await restored.get(job_id))["status"] != "running":
                await asyncio.sleep(0.01)
        assert remote.starts == []
    finally:
        await restored.close()


@pytest.mark.asyncio
async def test_active_scan_ignores_terminal_and_model_records_and_pages(fixture):
    _, service, _, _ = fixture
    async with service.store.sessions() as session:
        for i in range(11):
            data = {"id": f"id-{i:02d}", "status": "running" if i % 2 else "completed", "input_type": "images", "files": []}
            await session.execute(insert(jobs).values(id=data["id"], owner_id="admin", request_key=data["id"], created_at=datetime.now(UTC).isoformat(), revision=0, data_json=json.dumps(data)))
        await session.commit()
    result, cursor = [], None
    while True:
        page = await service.store.list_active(after_id=cursor, limit=2)
        result.extend(page)
        if len(page) < 2:
            break
        cursor = page[-1]["id"]
    assert len(result) == 5
    assert all(j["status"] == "running" for j in result)


@pytest.mark.asyncio
async def test_close_stops_monitor_without_cancelling_remote_job(fixture):
    _, service, remote, _ = fixture
    calls = []
    remote.cancel = lambda *args: calls.append(args)
    service.start_monitor(interval=10)
    service.start_monitor(interval=10)
    task = service.monitor_task
    await service.close()
    assert task.done()
    assert calls == []


@pytest.mark.asyncio
async def test_refresh_is_read_only_even_if_job_is_transferring(fixture):
    client, service, remote, _ = fixture
    response = await client.post("/api/reconstructions", data={"title": "重试隔离"}, files=files())
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))
    await service.store.patch(job_id, {"status": "transferring"})
    service.start = lambda *args: pytest.fail("GET must not submit training")
    await service.refresh(job_id)
    await asyncio.sleep(0)
    assert remote.starts == [job_id]


@pytest.mark.asyncio
async def test_missing_remote_after_grace_becomes_not_started(fixture):
    client, service, remote, _ = fixture
    response = await client.post("/api/reconstructions", data={"title": "未送达"}, files=files())
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))
    await service.store.patch(job_id, {"created_at": "2000-01-01T00:00:00+00:00"})
    remote.state = {"status": "transferring", "stage": "transferring", "remote_missing": True}
    result = await service.refresh(job_id)
    assert result["status"] == "failed"
    assert (await service.get(job_id))["error_code"] == "not_started"


@pytest.mark.asyncio
async def test_lifespan_starts_monitor_without_http_clients(fixture, monkeypatch):
    from app.gateway.routers import reconstructions

    _, service, _, app = fixture
    monkeypatch.setattr(reconstructions, "get_session_factory", lambda: service.store.sessions)
    app.state.reconstruction_service = service
    await reconstructions.start_service(app)
    assert service.monitor_task is not None
    assert not service.monitor_task.done()


@pytest.mark.asyncio
async def test_retry_requires_explicit_admin_post_and_preserves_id(fixture):
    client, service, remote, app = fixture
    response = await client.post("/api/reconstructions", data={"title": "显式重试"}, files=files())
    job_id = response.json()["id"]
    await asyncio.gather(*list(service.tasks.values()))
    await service.store.patch(job_id, {"status": "transferring"})
    result = await client.post(f"/api/reconstructions/{job_id}/retry-connection")
    assert result.status_code == 200
    assert result.json()["id"] == job_id
    await asyncio.gather(*list(service.tasks.values()))
    from app.gateway.routers import reconstructions

    app.dependency_overrides[reconstructions.get_current_user_from_request] = lambda: SimpleNamespace(id="reader", system_role="user")
    assert (await client.post(f"/api/reconstructions/{job_id}/retry-connection")).status_code == 403


@pytest.mark.asyncio
async def test_real_app_maps_wrapped_storage_errors_and_orders_auth():
    import errno

    from fastapi import Request
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from app.gateway.app import create_app
    from app.gateway.auth_middleware import AuthMiddleware
    from app.gateway.upload_storage_middleware import MapUploadStorageMiddleware

    app = create_app()
    classes = [item.cls for item in app.user_middleware]
    assert classes.index(AuthMiddleware) < classes.index(MapUploadStorageMiddleware)
    error = StarletteHTTPException(400, "There was an error parsing the body")
    error.__cause__ = OSError(errno.ENOSPC, "disk full")
    request = Request({"type": "http", "method": "POST", "path": "/api/reconstructions", "headers": []})
    response = await app.exception_handlers[StarletteHTTPException](request, error)
    assert response.status_code == 507
    assert json.loads(response.body)["error"]["code"] == "insufficient_storage"
