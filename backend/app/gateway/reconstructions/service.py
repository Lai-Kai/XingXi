from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from .config import IMAGE_EXTENSIONS, TERMINAL, VIDEO_EXTENSIONS, ReconstructionConfig
from .flux_pipeline import DEFAULT_PROMPT, PROFILE
from .store import JobStore


class ReconstructionService:
    def __init__(self, config: ReconstructionConfig, store: JobStore, remote):
        self.config, self.store, self.remote = config, store, remote
        self.tasks: dict[str, asyncio.Task] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    def public(self, job):
        fields = ("id", "title", "point_id", "point_name", "quality", "input_type", "status", "stage", "created_at", "log", "error", "connection_error", "cancel_requested")
        result = {key: job.get(key) for key in fields}
        result["files"] = [{"name": item["name"], "size": item["size"]} for item in job["files"]]
        result["preprocessing"] = job.get("preprocessing", "none")
        result["pipeline_profile"] = job.get("pipeline_profile", "direct")
        if job.get("preprocess_progress"):
            progress = dict(job["preprocess_progress"])
            if job.get("status") == "completed" and job.get("preprocessing") == "flux3":
                progress["completed"] = progress["total"]
            result["preprocess_progress"] = progress
        if job.get("artifact"):
            result["artifact"] = {key: job["artifact"][key] for key in ("size", "sha256", "kind", "splat_count", "point_count") if key in job["artifact"]}
            result["artifact_url"] = f"/api/reconstructions/{job['id']}/artifact/final.ply"
        return result

    async def create(self, uploads, *, owner_id, title, quality, point_id, point_name, request_id, preprocessing="none", preprocess_prompt=None, preprocess_seed=42):
        if preprocessing not in {"none", "flux3"}:
            raise HTTPException(400, "未知图片预处理方式")
        if preprocessing == "flux3" and not self.config.flux3_enabled:
            raise HTTPException(503, "FLUX3 预处理尚未配置，请联系管理员")
        prompt = (preprocess_prompt or DEFAULT_PROMPT).strip() or DEFAULT_PROMPT
        if not isinstance(preprocess_seed, int) or not 0 <= preprocess_seed <= 2**53 - 1 or len(prompt) > 4000:
            raise HTTPException(400, "FLUX3 提示词或种子无效")
        if not uploads or len(uploads) > self.config.max_files:
            raise HTTPException(400, "请选择一个视频或至少两张图片，最多 500 个文件")
        names = [item.filename or "" for item in uploads]
        if any(not name or "/" in name or "\\" in name or len(name) > 240 for name in names):
            raise HTTPException(400, "文件名无效")
        extensions = [Path(name).suffix.lower() for name in names]
        images = all(ext in IMAGE_EXTENSIONS for ext in extensions) and len(uploads) >= 2
        video = len(uploads) == 1 and extensions[0] in VIDEO_EXTENSIONS
        if not images and not video:
            raise HTTPException(400, "请上传一个视频或至少两张图片，不能混合上传")
        job_id = str(uuid.uuid4())
        directory = self.config.local_root / job_id
        await asyncio.to_thread((directory / "source").mkdir, parents=True, exist_ok=True)
        records, total = [], 0
        saved = False
        try:
            for index, (upload, extension) in enumerate(zip(uploads, extensions, strict=True)):
                stored_name = f"{index:05d}{extension}"
                path = directory / "source" / stored_name

                # One bounded chunk per worker call; never buffer a video in RAM.
                def copy_upload():
                    nonlocal total
                    digest = hashlib.sha256()
                    size = 0
                    with path.open("wb") as destination:
                        while block := upload.file.read(1024 * 1024):
                            total += len(block)
                            size += len(block)
                            if total > self.config.max_bytes:
                                raise HTTPException(413, "素材总大小超过 2 GiB")
                            digest.update(block)
                            destination.write(block)
                    if not size:
                        raise HTTPException(400, "不能上传空文件")
                    return {"name": upload.filename, "stored_name": stored_name, "size": size, "sha256": digest.hexdigest()}

                records.append(await asyncio.to_thread(copy_upload))
            identity = [title, quality, point_id, point_name, records]
            if preprocessing == "flux3":
                identity.append({"pipeline_profile": PROFILE, "prompt": prompt, "seed": preprocess_seed})
            fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            data = {
                "id": job_id,
                "owner_id": owner_id,
                "request_id": request_id or job_id,
                "title": title,
                "point_id": point_id,
                "point_name": point_name,
                "quality": quality,
                "input_type": "video" if video else "images",
                "files": records,
                "fingerprint": fingerprint,
                "status": "transferring",
                "stage": "transferring",
                "created_at": datetime.now(UTC).isoformat(),
                "log": "",
            }
            if preprocessing == "flux3":
                data.update(preprocessing="flux3", pipeline_profile=PROFILE, preprocess_prompt=prompt, preprocess_seed=preprocess_seed, flux3=self.config.flux3_snapshot())
            try:
                data, saved = await self.store.create(data)
            except ValueError as error:
                raise HTTPException(409, str(error)) from None
            if data["status"] == "transferring":
                self.start(data)
            return self.public(data)
        finally:
            if not saved:
                await asyncio.to_thread(shutil.rmtree, directory, ignore_errors=True)

    def start(self, job):
        job_id = job["id"]
        if job_id not in self.tasks or self.tasks[job_id].done():
            task = asyncio.create_task(self._submit(job), name="reconstruct-" + job_id)
            self.tasks[job_id] = task
            task.add_done_callback(lambda finished: self.tasks.pop(job_id, None) if self.tasks.get(job_id) is finished else None)

    async def _submit(self, job):
        try:
            state = await asyncio.to_thread(self.remote.submit, job, self.config.local_root / job["id"])
            await self.store.patch(job["id"], {**state, "connection_error": None})
        except Exception:
            # The SSH acknowledgement may be lost after a successful launch.
            # Keep the persistent ID and retry via the remote one-time claim.
            await self.store.patch(job["id"], {"connection_error": "远程连接暂不可用；可重试连接，任务不会重复启动"})

    async def get(self, job_id):
        job = await self.store.get(job_id)
        if job is None:
            raise HTTPException(404, "重建任务不存在")
        return job

    async def refresh(self, job_id):
        job = await self.get(job_id)
        if job["status"] in TERMINAL:
            return self.public(job)
        if job["status"] == "transferring":
            self.start(job)
            return self.public(job)
        async with self.locks.setdefault(job_id, asyncio.Lock()):
            try:
                state = await asyncio.to_thread(self.remote.inspect, job_id)
                job = await self.store.patch(job_id, {**state, "connection_error": None})
            except Exception:
                job = await self.store.patch(job_id, {"connection_error": "远程连接暂不可用，保留上次状态；请重试"})
        return self.public(job)

    async def cancel(self, job_id):
        job = await self.get(job_id)
        if job["status"] in TERMINAL:
            return self.public(job)
        job = await self.store.patch(job_id, {"cancel_requested": True})
        try:
            state = await asyncio.to_thread(self.remote.cancel, job_id)
            job = await self.store.patch(job_id, {**state, "connection_error": None})
        except Exception:
            job = await self.store.patch(job_id, {"connection_error": "取消请求尚未送达，请重试取消"})
        return self.public(job)

    async def artifact(self, job_id):
        job = await self.get(job_id)
        if job["status"] != "completed" or not job.get("artifact"):
            raise HTTPException(409, "重建结果尚不可用")
        async with self.locks.setdefault(job_id, asyncio.Lock()):
            path = self.config.local_root / job_id / "final.ply"
            if not await asyncio.to_thread(path.is_file):
                try:
                    await asyncio.to_thread(self.remote.download, job_id, job["artifact"], path)
                except Exception:
                    raise HTTPException(502, "结果下载失败，请重试连接") from None
        return path

    async def close(self):
        # Remote supervisors outlive the Gateway; no training process is cancelled here.
        if self.tasks:
            await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
