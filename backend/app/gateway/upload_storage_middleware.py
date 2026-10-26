"""Authenticate, admit, and bound map uploads before multipart form parsing."""

from __future__ import annotations

import asyncio
import errno
import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.gateway.errors import gateway_error_response
from app.gateway.reconstructions.config import ReconstructionConfig
from app.gateway.reconstructions.model_files import MAX_MODEL_BYTES
from app.gateway.reconstructions.storage import MULTIPART_OVERHEAD_BYTES, StorageBudget, insufficient_storage


class MapUploadStorageMiddleware:
    """Register before AuthMiddleware, so authentication/CSRF execute outside it.

    FastAPI parses Form parameters before route dependencies. A route dependency
    cannot protect the multipart spool. This middleware never reads the body
    before authentication, storage admission and the declared-length limit.
    """

    def __init__(self, app: ASGIApp, *, config_factory: Callable[[], ReconstructionConfig] = ReconstructionConfig, budget: StorageBudget | None = None, temp_root: Path | None = None):
        self.app = app
        self.config_factory = config_factory
        self.budget = budget or StorageBudget()
        self.temp_root = temp_root

    def _reserve(self, scope: Scope, content_length: int | None):
        service = getattr(scope["app"].state, "reconstruction_service", None)
        config = service.config if service is not None else self.config_factory()
        max_bytes = min(config.max_bytes, MAX_MODEL_BYTES) if scope["path"].rstrip("/") == "/api/map/model-assets" else config.max_bytes
        max_body = max_bytes + MULTIPART_OVERHEAD_BYTES
        if content_length is not None and content_length > max_body:
            raise HTTPException(413, "上传内容超过大小限制（重建素材最多 2 GiB，模型最多 256 MiB）")
        body_budget = max_body if content_length is None else content_length
        temporary = self.temp_root if self.temp_root is not None else Path(tempfile.gettempdir())
        return self.budget.reserve(temporary, config.local_root, body_budget, min(body_budget, max_bytes)), body_budget

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") not in {"/api/reconstructions", "/api/map/model-assets"}:
            await self.app(scope, receive, send)
            return

        user = scope.get("state", {}).get("user")
        if user is None or getattr(user, "system_role", None) != "admin":
            response = gateway_error_response(401 if user is None else 403, "仅管理员可上传地图模型或提交影像重建")
            await response(scope, receive, send)
            return

        reservation = None
        response_started = False
        try:
            lengths = Headers(scope=scope).getlist("content-length")
            if len(lengths) > 1 or (lengths and (not lengths[0].isascii() or not lengths[0].isdigit())):
                raise HTTPException(400, "Content-Length 无效")
            if lengths and len(lengths[0]) > 20:
                raise HTTPException(413, "上传内容超过大小限制")
            content_length = int(lengths[0]) if lengths else None
            pending = asyncio.create_task(asyncio.to_thread(self._reserve, scope, content_length))
            try:
                reservation, body_budget = await asyncio.shield(pending)
            except asyncio.CancelledError:
                # Cancelling to_thread does not stop its thread. Release its
                # eventual admission even if the client disconnected meanwhile.
                def release_pending(finished):
                    if not finished.cancelled() and finished.exception() is None:
                        finished.result()[0].release()

                pending.add_done_callback(release_pending)
                raise
            received = 0

            async def bounded_receive() -> Message:
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > body_budget:
                        raise HTTPException(413, "上传内容超过声明大小或上传限制")
                return message

            async def track_send(message: Message) -> None:
                nonlocal response_started
                if message["type"] == "http.response.start":
                    response_started = True
                await send(message)

            await self.app(scope, bounded_receive, track_send)
        except HTTPException as error:
            if response_started:
                raise
            await gateway_error_response(error.status_code, error.detail)(scope, receive, send)
        except OSError as error:
            if response_started or error.errno not in {errno.ENOSPC, errno.EDQUOT}:
                raise
            failure = insufficient_storage()
            await gateway_error_response(failure.status_code, failure.detail)(scope, receive, send)
        finally:
            if reservation is not None:
                reservation.release()
