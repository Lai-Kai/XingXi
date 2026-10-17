"""Administrator-only map reconstruction entry. No GPU probes or scheduling."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile

from app.gateway.deps import get_current_user_from_request
from app.gateway.reconstructions.config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, ReconstructionConfig
from app.gateway.reconstructions.service import ReconstructionService
from app.gateway.reconstructions.ssh import SSHRemote
from app.gateway.reconstructions.store import JobStore
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/reconstructions", tags=["reconstructions"])


async def admin(user=Depends(get_current_user_from_request)):
    if user.system_role != "admin":
        raise HTTPException(403, "仅管理员可使用影像重建")
    return user


async def get_service(request: Request):
    service = getattr(request.app.state, "reconstruction_service", None)
    if service is None:
        sessions = get_session_factory()
        if sessions is None:
            raise HTTPException(503, "任务数据库不可用")
        config = await asyncio.to_thread(ReconstructionConfig)
        # Concurrent first requests may have finished initialization while resolving paths.
        service = getattr(request.app.state, "reconstruction_service", None)
        if service is None:
            service = ReconstructionService(config, JobStore(sessions), SSHRemote(config))
            request.app.state.reconstruction_service = service
    return service


@router.get("/capabilities")
async def capabilities(user=Depends(admin), service=Depends(get_service)):
    config = service.config
    return {"enabled": await asyncio.to_thread(lambda: config.enabled), "max_bytes": config.max_bytes, "max_files": config.max_files, "extensions": sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)}


@router.post("", status_code=202)
async def create(
    request: Request,
    title: Annotated[str, Form(min_length=1, max_length=120)],
    quality: Annotated[Literal["fast", "balanced", "high"], Form()] = "balanced",
    point_id: Annotated[str | None, Form(max_length=255)] = None,
    point_name: Annotated[str | None, Form(max_length=255)] = None,
    request_id: Annotated[str | None, Form(max_length=128)] = None,
    user=Depends(admin),
    service=Depends(get_service),
):
    if isinstance(service.remote, SSHRemote) and not await asyncio.to_thread(lambda: service.config.enabled):
        raise HTTPException(503, "请先配置 SSH 连接、可信主机公钥并安装 reconstruction 依赖")
    async with request.form(max_files=service.config.max_files, max_part_size=service.config.max_bytes) as form:
        if not title.strip():
            raise HTTPException(422, "请填写重建名称")
        uploads = form.getlist("files")
        if not all(isinstance(item, UploadFile) for item in uploads):
            raise HTTPException(400, "素材格式无效")
        return await service.create(uploads, owner_id=str(user.id), title=title.strip(), quality=quality, point_id=point_id, point_name=point_name, request_id=request_id)


@router.get("")
async def listing(point_id: str | None = None, user=Depends(admin), service=Depends(get_service)):
    return [service.public(job) for job in await service.store.list(point_id) if job.get("input_type") != "model"]


@router.get("/{job_id}")
async def detail(job_id: str, user=Depends(admin), service=Depends(get_service)):
    return await service.refresh(job_id)


@router.post("/{job_id}/cancel")
async def cancel(job_id: str, user=Depends(admin), service=Depends(get_service)):
    return await service.cancel(job_id)


@router.get("/{job_id}/artifact/final.ply")
async def artifact(job_id: str, user=Depends(admin), service=Depends(get_service)):
    path = await service.artifact(job_id)
    return FileResponse(path, media_type="application/octet-stream", filename="final.ply", headers={"Cache-Control": "private, no-store"})
