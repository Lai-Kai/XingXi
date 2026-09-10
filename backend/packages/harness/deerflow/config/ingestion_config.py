from pydantic import BaseModel, Field


class IngestionConfig(BaseModel):
    """Historical-source ingestion job scheduling limits."""

    max_concurrent_jobs: int = Field(default=2, ge=1, le=32, description="Maximum ingestion jobs allowed to run across workers")
    lease_seconds: int = Field(default=60, ge=10, le=3600, description="Worker lease duration for a running ingestion step")
    recovery_grace_seconds: int = Field(default=10, ge=0, le=300, description="Additional grace before an expired ingestion lease is recovered")
    auto_publish_internal_release: bool = Field(
        default=True,
        description="Build a complete internal working release after chunking sources authorized for internal processing",
    )
