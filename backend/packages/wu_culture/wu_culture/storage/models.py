from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ObjectKind(StrEnum):
    ORIGINAL = "original"
    PAGE_IMAGE = "page_image"
    DERIVED = "derived"


class StorageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PutObjectRequest(StorageModel):
    owner_id: str = Field(min_length=1)
    kind: ObjectKind
    content: bytes = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    original_filename: str | None = None


class StoredObject(StorageModel):
    object_key: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    kind: ObjectKind
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str = Field(min_length=1)
    size: int = Field(ge=1)
    backend: str = Field(min_length=1)
    storage_uri: str = Field(min_length=1)
    original_filename: str | None = None
    created_at: datetime


class StoredObjectContent(StorageModel):
    metadata: StoredObject
    content: bytes


class DeleteResult(StorageModel):
    metadata: StoredObject
    reason: str = Field(min_length=1)
    deleted_at: datetime


class ObjectStorage(Protocol):
    async def put(self, request: PutObjectRequest) -> StoredObject: ...

    async def get(self, *, owner_id: str, object_key: str) -> StoredObjectContent: ...

    async def stat(self, *, owner_id: str, object_key: str) -> StoredObject: ...

    async def delete(self, *, owner_id: str, object_key: str, reason: str) -> DeleteResult: ...


class ObjectMetadataRepository(Protocol):
    async def save(self, metadata: StoredObject) -> None: ...

    async def get(self, *, owner_id: str, object_key: str) -> StoredObject | None: ...
