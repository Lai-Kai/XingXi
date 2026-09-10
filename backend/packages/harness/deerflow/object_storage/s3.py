from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import uuid4

from wu_culture.storage import DeleteResult, PutObjectRequest, StoredObject, StoredObjectContent

from deerflow.config.object_storage_config import ObjectStorageConfig

from .local import ObjectNotFoundError

_SAFE_OWNER_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_METADATA_FIELD = "xingxi-object"


class S3ObjectStorage:
    """S3-compatible object storage adapter supporting AWS S3 and MinIO."""

    def __init__(self, config: ObjectStorageConfig, *, client=None) -> None:
        if config.backend != "s3" or not config.bucket:
            raise ValueError("S3ObjectStorage requires an s3 config with a bucket")
        self._config = config
        self._bucket = config.bucket
        self._prefix = config.prefix.strip("/")
        self._client = client or self._build_client(config)

    @staticmethod
    def _build_client(config: ObjectStorageConfig):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("S3 object storage requires the 's3' optional dependency") from exc

        return boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            region_name=config.region,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            aws_session_token=config.session_token,
            config=Config(s3={"addressing_style": config.addressing_style}),
        )

    async def put(self, request: PutObjectRequest) -> StoredObject:
        return await asyncio.to_thread(self._put_sync, request)

    def _put_sync(self, request: PutObjectRequest) -> StoredObject:
        self._validate_owner_id(request.owner_id)
        digest = hashlib.sha256(request.content).hexdigest()
        object_key = f"users/{request.owner_id}/objects/{request.kind.value}/{digest[:2]}/{digest}"
        backend_key = self._backend_key(object_key)
        try:
            existing = self._metadata_from_response(self._client.head_object(Bucket=self._bucket, Key=backend_key))
            if existing.sha256 == digest and existing.size == len(request.content):
                return existing
        except Exception as exc:
            if not self._is_not_found(exc):
                raise

        metadata = StoredObject(
            object_key=object_key,
            owner_id=request.owner_id,
            kind=request.kind,
            sha256=digest,
            mime_type=request.mime_type,
            size=len(request.content),
            backend="s3",
            storage_uri=f"s3://{self._bucket}/{backend_key}",
            original_filename=request.original_filename,
            created_at=datetime.now(UTC),
        )
        self._client.put_object(
            Bucket=self._bucket,
            Key=backend_key,
            Body=request.content,
            ContentType=request.mime_type,
            Metadata={_METADATA_FIELD: self._encode_metadata(metadata)},
        )
        return metadata

    async def get(self, *, owner_id: str, object_key: str) -> StoredObjectContent:
        return await asyncio.to_thread(self._get_sync, owner_id, object_key)

    def _get_sync(self, owner_id: str, object_key: str) -> StoredObjectContent:
        backend_key = self._authorized_backend_key(owner_id, object_key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=backend_key)
        except Exception as exc:
            if self._is_not_found(exc):
                raise ObjectNotFoundError("Object not found") from exc
            raise
        metadata = self._metadata_from_response(response)
        if metadata.owner_id != owner_id:
            raise ObjectNotFoundError("Object not found")
        return StoredObjectContent(metadata=metadata, content=response["Body"].read())

    async def stat(self, *, owner_id: str, object_key: str) -> StoredObject:
        return await asyncio.to_thread(self._stat_sync, owner_id, object_key)

    def _stat_sync(self, owner_id: str, object_key: str) -> StoredObject:
        backend_key = self._authorized_backend_key(owner_id, object_key)
        try:
            metadata = self._metadata_from_response(self._client.head_object(Bucket=self._bucket, Key=backend_key))
        except Exception as exc:
            if self._is_not_found(exc):
                raise ObjectNotFoundError("Object not found") from exc
            raise
        if metadata.owner_id != owner_id:
            raise ObjectNotFoundError("Object not found")
        return metadata

    async def delete(self, *, owner_id: str, object_key: str, reason: str) -> DeleteResult:
        if not reason.strip():
            raise ValueError("delete reason is required")
        return await asyncio.to_thread(self._delete_sync, owner_id, object_key, reason.strip())

    def _delete_sync(self, owner_id: str, object_key: str, reason: str) -> DeleteResult:
        metadata = self._stat_sync(owner_id, object_key)
        deleted = DeleteResult(metadata=metadata, reason=reason, deleted_at=datetime.now(UTC))
        audit_key = self._backend_key(f"audit/deletions/{deleted.deleted_at:%Y/%m/%d}/{uuid4()}.json")
        self._client.put_object(
            Bucket=self._bucket,
            Key=audit_key,
            Body=deleted.model_dump_json().encode(),
            ContentType="application/json",
        )
        self._client.delete_object(Bucket=self._bucket, Key=self._backend_key(object_key))
        return deleted

    def _authorized_backend_key(self, owner_id: str, object_key: str) -> str:
        self._validate_owner_id(owner_id)
        key = PurePosixPath(object_key)
        if key.is_absolute() or "\\" in object_key or ":" in object_key or ".." in key.parts or len(key.parts) < 4:
            raise ValueError("invalid object_key")
        if key.parts[0] != "users" or key.parts[2] != "objects":
            raise ValueError("invalid object_key")
        if key.parts[1] != owner_id:
            raise ObjectNotFoundError("Object not found")
        return self._backend_key(object_key)

    def _backend_key(self, object_key: str) -> str:
        return f"{self._prefix}/{object_key}" if self._prefix else object_key

    @staticmethod
    def _validate_owner_id(owner_id: str) -> None:
        if not _SAFE_OWNER_ID.fullmatch(owner_id):
            raise ValueError("owner_id may contain only letters, numbers, hyphens, and underscores")

    @staticmethod
    def _encode_metadata(metadata: StoredObject) -> str:
        return base64.urlsafe_b64encode(metadata.model_dump_json().encode()).decode()

    @staticmethod
    def _metadata_from_response(response) -> StoredObject:
        encoded = response.get("Metadata", {}).get(_METADATA_FIELD)
        if not encoded:
            raise ValueError("Object is missing Xingxi storage metadata")
        return StoredObject.model_validate_json(base64.urlsafe_b64decode(encoded).decode())

    @staticmethod
    def _is_not_found(exc: Exception) -> bool:
        if isinstance(exc, KeyError):
            return True
        response = getattr(exc, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchKey", "NotFound"}
