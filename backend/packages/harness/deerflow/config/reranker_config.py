from pydantic import BaseModel, Field


class RerankerConfig(BaseModel):
    """HTTP reranker settings for Jina/Cohere-compatible responses."""

    enabled: bool = Field(default=False, description="Enable candidate reranking")
    model: str = Field(default="jina-reranker-v2-base-multilingual", description="Provider model identifier")
    api_key: str | None = Field(default=None, description="Provider API key or environment-resolved value")
    base_url: str | None = Field(default=None, description="Provider API base URL")
    endpoint: str = Field(default="/rerank", description="Rerank endpoint path")
    candidate_limit: int = Field(default=50, ge=1, le=1000, description="Maximum candidates sent to the provider")
    batch_size: int = Field(default=50, ge=1, le=1000, description="Maximum candidates per provider request")
    timeout: float = Field(default=30.0, gt=0, description="Provider request timeout in seconds")
    max_retries: int = Field(default=2, ge=0, le=10, description="Retries after the initial request")
    fail_open: bool = Field(default=True, description="Keep original order when the provider fails")

