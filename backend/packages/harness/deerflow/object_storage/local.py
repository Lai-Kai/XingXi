from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from wu_culture.storage import DeleteResult, PutObjectRequest, StoredObject, StoredObjectContent


class ObjectNotFoundError(FileNotFoundError):
    pass


_SAFE_OWNER_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class LocalObjectStorage:
    """Persistent content-addressed object storage rooted in one controlled directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    async def put(self, request: PutObjectRequest) -> StoredObject:
        return await asyncio.to_thread(self._put_sync, request)

    def _put_sync(self, request: PutObjectRequest) -> StoredObject:
        self._validate_owner_id(request.owner_id)
        digest = hashlib.sha256(request.content).hexdigest()
        object_key = f"users/{request.owner_id}/objects/{request.kind.value}/{digest[:2]}/{digest}"
        object_path = self._resolve_object_path(request.owner_id, object_key)
        metadata_path = object_path.with_name(f"{object_path.name}.metadata.json")
        object_path.parent.mkdir(parents=True, exist_ok=True)

        if object_path.is_file() and metadata_path.is_file():
            existing = StoredObject.model_validate_json(metadata_path.read_text(encoding="utf-8"))
            if existing.sha256 == digest and existing.size == len(request.content):
                return existing

        metadata = StoredObject(
            object_key=object_key,
            owner_id=request.owner_id,
            kind=request.kind,
            sha256=digest,
            mime_type=request.mime_type,
            size=len(request.content),
            backend="local",
            storage_uri=object_path.as_uri(),
            original_filename=request.original_filename,
            created_at=datetime.now(UTC),
        )
        self._atomic_write(object_path, request.content)
        self._atomic_write(metadata_path, metadata.model_dump_json(indent=2).encode())
        return metadata

    async def get(self, *, owner_id: str, object_key: str) -> StoredObjectContent:
        return await asyncio.to_thread(self._get_sync, owner_id, object_key)

    def _get_sync(self, owner_id: str, object_key: str) -> StoredObjectContent:
        object_path = self._resolve_object_path(owner_id, object_key)
        metadata_path = object_path.with_name(f"{object_path.name}.metadata.json")
        try:
            metadata = StoredObject.model_validate(json.loads(metadata_path.read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise ObjectNotFoundError("Object not found") from exc
        if metadata.owner_id != owner_id:
            raise ObjectNotFoundError("Object not found")
        try:
            content = object_path.read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFoundError("Object not found") from exc
        return StoredObjectContent(metadata=metadata, content=content)

    async def stat(self, *, owner_id: str, object_key: str) -> StoredObject:
        result = await self.get(owner_id=owner_id, object_key=object_key)
        return result.metadata

    async def delete(self, *, owner_id: str, object_key: str, reason: str) -> DeleteResult:
        if not reason.strip():
            raise ValueError("delete reason is required")
        return await asyncio.to_thread(self._delete_sync, owner_id, object_key, reason.strip())

    def _delete_sync(self, owner_id: str, object_key: str, reason: str) -> DeleteResult:
        result = self._get_sync(owner_id, object_key)
        object_path = self._resolve_object_path(owner_id, object_key)
        metadata_path = object_path.with_name(f"{object_path.name}.metadata.json")
        deleted = DeleteResult(metadata=result.metadata, reason=reason, deleted_at=datetime.now(UTC))
        audit_path = self._root / "deletion-audit.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(deleted.model_dump_json() + "\n")
        object_path.unlink()
        metadata_path.unlink()
        return deleted

    @staticmethod
    def _validate_owner_id(owner_id: str) -> None:
        if not _SAFE_OWNER_ID.fullmatch(owner_id):
            raise ValueError("owner_id may contain only letters, numbers, hyphens, and underscores")

    def _resolve_object_path(self, owner_id: str, object_key: str) -> Path:
        self._validate_owner_id(owner_id)
        key = PurePosixPath(object_key)
        if key.is_absolute() or "\\" in object_key or ":" in object_key or ".." in key.parts or len(key.parts) < 4 or key.parts[0] != "users" or key.parts[2] != "objects":
            raise ValueError("invalid object_key")
        if key.parts[1] != owner_id:
            raise ObjectNotFoundError("Object not found")
        resolved = (self._root / Path(*key.parts)).resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("invalid object_key") from exc
        return resolved

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
