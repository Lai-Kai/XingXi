from pydantic import BaseModel, Field


class EmbeddingConfig(BaseModel):
    """OpenAI-compatible embedding provider settings."""

    enabled: bool = Field(default=False, description="Enable embedding generation")
    model: str = Field(default="text-embedding-3-small", description="Embedding model identifier")
    version: str = Field(default="v1", min_length=1, description="Explicit embedding/index compatibility version")
    api_key: str | None = Field(default=None, description="Provider API key or environment-resolved value")
    base_url: str | None = Field(default=None, description="OpenAI-compatible API base URL")
    dimensions: int | None = Field(default=None, ge=1, description="Expected output vector dimension")
    batch_size: int = Field(default=32, ge=1, le=2048, description="Maximum texts per provider request")
    timeout: float = Field(default=60.0, gt=0, description="Provider request timeout in seconds")
    max_retries: int = Field(default=2, ge=0, le=10, description="Provider retry count")

    @property
    def identity(self) -> str:
        dimensions = str(self.dimensions) if self.dimensions is not None else "auto"
        return f"{self.model}:{self.version}:{dimensions}"
