from pydantic import BaseModel, Field


class HybridSearchConfig(BaseModel):
    """Deterministic lexical/vector fusion settings."""

    channel_timeout_seconds: float = Field(default=5.0, gt=0, le=120)
    rrf_k: int = Field(default=60, ge=1, le=1000)
