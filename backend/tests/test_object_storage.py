from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
import yaml
from wu_culture.storage import ObjectKind, PutObjectRequest

from deerflow.config.object_storage_config import ObjectStorageConfig
from deerflow.object_storage import LocalObjectStorage, ObjectNotFoundError, S3ObjectStorage, create_object_storage

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_local_object_store_round_trips_bytes_and_metadata_after_recreation(tmp_path):
    asyncio.run(_round_trip_after_recreation(tmp_path))


async def _round_trip_after_recreation(tmp_path):
    content = "木渎历史资料".encode()
    request = PutObjectRequest(
        owner_id="researcher-1",
        kind=ObjectKind.ORIGINAL,
        content=content,
        mime_type="text/plain",
        original_filename="mudu.txt",
    )

    stored = await LocalObjectStorage(tmp_path).put(request)
    result = await LocalObjectStorage(tmp_path).get(
        owner_id=request.owner_id,
        object_key=stored.object_key,
    )

    assert result.content == content
    assert result.metadata.sha256 == hashlib.sha256(content).hexdigest()
    assert result.metadata.size == len(content)
    assert result.metadata.mime_type == "text/plain"
    assert result.metadata.kind is ObjectKind.ORIGINAL
    assert result.metadata.owner_id == request.owner_id
    assert result.metadata.backend == "local"
    assert result.metadata.storage_uri.startswith("file://")


def test_missing_object_has_typed_not_found_error(tmp_path):
    async def exercise():
        store = LocalObjectStorage(tmp_path)
        with pytest.raises(ObjectNotFoundError, match="Object not found"):
            await store.get(owner_id="researcher-1", object_key="users/researcher-1/objects/original/aa/missing")

    asyncio.run(exercise())


def test_local_object_store_rejects_paths_outside_its_root(tmp_path):
    async def exercise():
        store = LocalObjectStorage(tmp_path)
        unsafe_request = PutObjectRequest(
            owner_id="../../other-user",
            kind=ObjectKind.ORIGINAL,
            content=b"private",
            mime_type="text/plain",
        )
        with pytest.raises(ValueError, match="owner_id"):
            await store.put(unsafe_request)
        with pytest.raises(ValueError, match="object_key"):
            await store.get(owner_id="researcher-1", object_key="../outside")

    asyncio.run(exercise())


def test_other_owner_cannot_read_or_delete_object(tmp_path):
    async def exercise():
        store = LocalObjectStorage(tmp_path)
        stored = await store.put(
            PutObjectRequest(
                owner_id="researcher-1",
                kind=ObjectKind.ORIGINAL,
                content=b"private source",
                mime_type="text/plain",
            )
        )

        with pytest.raises(ObjectNotFoundError):
            await store.get(owner_id="researcher-2", object_key=stored.object_key)
        with pytest.raises(ObjectNotFoundError):
            await store.delete(owner_id="researcher-2", object_key=stored.object_key, reason="not mine")

        assert (await store.get(owner_id="researcher-1", object_key=stored.object_key)).content == b"private source"

    asyncio.run(exercise())


def test_duplicate_content_is_one_immutable_object(tmp_path):
    async def exercise():
        store = LocalObjectStorage(tmp_path)
        first = await store.put(
            PutObjectRequest(
                owner_id="researcher-1",
                kind=ObjectKind.ORIGINAL,
                content=b"same source",
                mime_type="text/plain",
                original_filename="first.txt",
            )
        )
        duplicate = await store.put(
            PutObjectRequest(
                owner_id="researcher-1",
                kind=ObjectKind.ORIGINAL,
                content=b"same source",
                mime_type="text/plain",
                original_filename="renamed.txt",
            )
        )

        assert duplicate == first
        assert len(list(tmp_path.rglob(first.sha256))) == 1

    asyncio.run(exercise())


def test_delete_requires_reason_and_leaves_audit_record(tmp_path):
    async def exercise():
        store = LocalObjectStorage(tmp_path)
        stored = await store.put(
            PutObjectRequest(
                owner_id="researcher-1",
                kind=ObjectKind.DERIVED,
                content=b"ocr output",
                mime_type="text/plain",
            )
        )
        with pytest.raises(ValueError, match="reason"):
            await store.delete(owner_id="researcher-1", object_key=stored.object_key, reason="  ")

        deleted = await store.delete(
            owner_id="researcher-1",
            object_key=stored.object_key,
            reason="source registration withdrawn",
        )

        assert deleted.metadata == stored
        assert deleted.reason == "source registration withdrawn"
        audit = (tmp_path / "deletion-audit.jsonl").read_text(encoding="utf-8")
        assert stored.object_key in audit
        assert "source registration withdrawn" in audit
        with pytest.raises(ObjectNotFoundError):
            await store.get(owner_id="researcher-1", object_key=stored.object_key)

    asyncio.run(exercise())


def test_factory_builds_runnable_local_store_from_config(tmp_path):
    async def exercise():
        store = create_object_storage(ObjectStorageConfig(backend="local", local_dir=str(tmp_path)))
        stored = await store.put(
            PutObjectRequest(
                owner_id="researcher-1",
                kind=ObjectKind.PAGE_IMAGE,
                content=b"page image",
                mime_type="image/png",
            )
        )

        assert isinstance(store, LocalObjectStorage)
        assert (await store.stat(owner_id="researcher-1", object_key=stored.object_key)) == stored

    asyncio.run(exercise())


def test_s3_compatible_store_round_trips_through_configured_bucket():
    class Body:
        def __init__(self, content):
            self._content = content

        def read(self):
            return self._content

    class FakeS3Client:
        def __init__(self):
            self.objects = {}

        def put_object(self, **kwargs):
            self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs

        def get_object(self, *, Bucket, Key):
            item = self.objects[(Bucket, Key)]
            return {"Body": Body(item["Body"]), "Metadata": item["Metadata"]}

        def head_object(self, *, Bucket, Key):
            item = self.objects[(Bucket, Key)]
            return {"Metadata": item["Metadata"]}

        def delete_object(self, *, Bucket, Key):
            self.objects.pop((Bucket, Key))

    async def exercise():
        client = FakeS3Client()
        config = ObjectStorageConfig(
            backend="s3",
            bucket="historical-sources",
            endpoint_url="http://minio:9000",
            prefix="xingxi-test",
        )
        store = create_object_storage(config, s3_client=client)
        stored = await store.put(
            PutObjectRequest(
                owner_id="researcher-1",
                kind=ObjectKind.PAGE_IMAGE,
                content=b"page image",
                mime_type="image/png",
                original_filename="page-001.png",
            )
        )
        result = await S3ObjectStorage(config, client=client).get(
            owner_id="researcher-1",
            object_key=stored.object_key,
        )

        assert isinstance(store, S3ObjectStorage)
        assert result.content == b"page image"
        assert result.metadata == stored
        assert stored.storage_uri.startswith("s3://historical-sources/xingxi-test/")

    asyncio.run(exercise())


def test_docker_gateway_persists_default_local_object_directory():
    compose = yaml.safe_load((REPO_ROOT / "docker" / "docker-compose.yaml").read_text(encoding="utf-8"))
    gateway = compose["services"]["gateway"]

    assert "${DEER_FLOW_HOME}:/app/backend/.deer-flow" in gateway["volumes"]
    assert "DEER_FLOW_HOME=/app/backend/.deer-flow" in gateway["environment"]
    assert ObjectStorageConfig().local_dir == "objects"
