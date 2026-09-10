from __future__ import annotations

from pathlib import Path

from deerflow.config.object_storage_config import ObjectStorageConfig
from deerflow.config.runtime_paths import runtime_home

from .local import LocalObjectStorage
from .s3 import S3ObjectStorage


def create_object_storage(config: ObjectStorageConfig, *, s3_client=None):
    if config.backend == "local":
        root = Path(config.local_dir)
        if not root.is_absolute():
            root = runtime_home() / root
        return LocalObjectStorage(root)
    if config.backend == "s3":
        return S3ObjectStorage(config, client=s3_client)
    raise ValueError(f"Unsupported object storage backend: {config.backend}")
