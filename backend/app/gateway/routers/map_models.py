"""Persistent map model assets, backed by existing reconstruction records."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile

from app.gateway.deps import get_current_user_from_request
from app.gateway.reconstructions import model_files
from app.gateway.routers import map_points
from app.gateway.routers.reconstructions import admin, get_service

router = APIRouter(prefix="/api/map/model-assets", tags=["map-models"])


async def get_model_points(source=Depends(map_points.get_versioned_catalog_source)):
    catalog = await map_points.get_map_catalog(source)
    # Match the browser's exact ID-based merge of curated references and Release points.
    return {point.id: point for point in [*map_points.POINTS, *catalog.points]}


def descriptor(job, points):
    point = points.get(job.get("point_id"))
    artifact = job.get("artifact")
    if point is None or job.get("status") != "completed" or not artifact or job.get("entity_id", point.entity_id) != point.entity_id:
        return None
    format_ = artifact.get("format", "ply")
    kind = artifact.get("kind", "gaussian")
    if format_ not in {"ply", "glb"} or kind not in {"gaussian", "point_cloud", "mesh"}:
        return None
    url = f"/api/map/model-assets/{job['id']}/file"
    return {
        "id": job["id"],
        "point_id": point.id,
        "entity_id": point.entity_id,
        "title": job["title"],
        "format": format_,
        "kind": kind,
        "size_bytes": artifact["size"],
        "sha256": artifact["sha256"],
        "source": "upload" if job.get("input_type") == "model" else "reconstruction",
        "created_at": job["created_at"],
        "preview_url": url,
        "download_url": url + "?download=true",
        **{key: artifact[key] for key in ("point_count", "splat_count") if key in artifact},
    }


@router.get("")
async def listing(point_id: str | None = None, user=Depends(get_current_user_from_request), points=Depends(get_model_points), service=Depends(get_service)):
    records = await service.store.list(point_id, limit=1000)
    return [asset for job in records if (asset := descriptor(job, points)) is not None]


@router.post("", status_code=201)
async def create(
    request: Request,
    title: Annotated[str, Form(min_length=1, max_length=120)],
    point_id: Annotated[str, Form(min_length=1, max_length=255)],
    request_id: Annotated[str | None, Form(max_length=128)] = None,
    user=Depends(admin),
    points=Depends(get_model_points),
    service=Depends(get_service),
):
    if not title.strip():
        raise HTTPException(422, "请填写模型名称")
    point = points.get(point_id)
    if point is None:
        raise HTTPException(404, "请选择地图中已有的点位")
    max_bytes = min(model_files.MAX_MODEL_BYTES, service.config.max_bytes)
    job_id = str(uuid4())
    directory = service.config.local_root / job_id
    saved = False
    try:
        async with request.form(max_files=2, max_fields=8, max_part_size=max_bytes) as form:
            uploads = [value for _, value in form.multi_items() if isinstance(value, UploadFile)]
            if len(uploads) != 1 or form.get("file") is not uploads[0]:
                raise HTTPException(400, "每次请选择一个 PLY 或 GLB 模型")
            upload = uploads[0]
            artifact = await asyncio.to_thread(model_files.copy_model, upload.file, directory, upload.filename or "", max_bytes)
            fingerprint = hashlib.sha256(json.dumps(["model", title.strip(), point_id, point.entity_id, artifact["sha256"], artifact["format"]], ensure_ascii=False).encode()).hexdigest()
            data = {
                "id": job_id,
                "owner_id": str(user.id),
                "point_id": point_id,
                "entity_id": point.entity_id,
                "point_name": point.name,
                "title": title.strip(),
                "request_id": request_id or job_id,
                "fingerprint": fingerprint,
                "created_at": datetime.now(UTC).isoformat(),
                "input_type": "model",
                "quality": "imported",
                "status": "completed",
                "stage": "imported",
                "artifact": artifact,
                "files": [{"name": upload.filename, "size": artifact["size"]}],
                "log": "",
            }
            try:
                job, saved = await service.store.create(data)
            except ValueError as error:
                raise HTTPException(409, str(error)) from None
            return descriptor(job, points)
    finally:
        if not saved:
            # Only this request's server-generated UUID directory may be removed.
            directory.resolve().relative_to(service.config.local_root.resolve())
            await asyncio.to_thread(shutil.rmtree, directory, ignore_errors=True)


@router.get("/{asset_id}/file")
async def file(asset_id: UUID, download: bool = False, user=Depends(get_current_user_from_request), points=Depends(get_model_points), service=Depends(get_service)):
    job = await service.get(str(asset_id))
    asset = descriptor(job, points)
    if asset is None:
        raise HTTPException(404, "模型尚未就绪或已不在当前地图中")
    if job.get("input_type") == "model":
        path = service.config.local_root / str(asset_id) / ("model." + asset["format"])
        if not await asyncio.to_thread(path.is_file):
            raise HTTPException(404, "模型文件不存在")
    else:
        path = await service.artifact(str(asset_id))
    return FileResponse(
        path,
        filename="model." + asset["format"],
        content_disposition_type="attachment" if download else "inline",
        media_type="model/gltf-binary" if asset["format"] == "glb" else "application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )
