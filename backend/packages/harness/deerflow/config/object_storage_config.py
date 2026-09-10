from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ObjectStorageConfig(BaseModel):
    """Storage for historical-source originals, page images, and derived files."""

    backend: Literal["local", "s3"] = "local"
    local_dir: str = Field(default="objects", min_length=1)
    bucket: str | None = None
    endpoint_url: str | None = None
    region: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    prefix: str = "xingxi"
    addressing_style: Literal["auto", "path", "virtual"] = "path"

    @model_validator(mode="after")
    def validate_backend_settings(self) -> ObjectStorageConfig:
        if self.backend == "s3" and not self.bucket:
            raise ValueError("object_storage.bucket is required for the s3 backend")
        return self
