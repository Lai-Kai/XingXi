from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from deerflow.config.embedding_config import EmbeddingConfig


class EmbeddingService:
    """Generate and validate vectors without exposing partial batch results."""

    def __init__(self, config: EmbeddingConfig, *, embeddings_factory: Callable[..., Any] | None = None) -> None:
        if not config.enabled:
            raise ValueError("Embedding service is disabled; set embedding.enabled=true")
        self.config = config
        self._factory = embeddings_factory
        self._provider: Any | None = None

    def _get_provider(self) -> Any:
        if self._provider is None:
            factory = self._factory
            if factory is None:
                from langchain_openai import OpenAIEmbeddings

                factory = OpenAIEmbeddings
            kwargs: dict[str, Any] = {
                "model": self.config.model,
                "api_key": self.config.api_key,
                "base_url": self.config.base_url,
                "dimensions": self.config.dimensions,
                "timeout": self.config.timeout,
                "max_retries": self.config.max_retries,
            }
            self._provider = factory(**{key: value for key, value in kwargs.items() if value is not None})
        return self._provider

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch, preserving order and rejecting partial/invalid output."""
        if not texts:
            return []
        normalized = [text if isinstance(text, str) else str(text) for text in texts]
        vectors: list[list[float] | None] = [None] * len(normalized)
        non_empty = [(index, text) for index, text in enumerate(normalized) if text.strip()]
        dimension = self.config.dimensions

        # Empty chunks get an explicit zero vector so they cannot be sent to the
        # provider or silently shift indexes in a persisted batch.
        if dimension is not None:
            zero = [0.0] * dimension
            for index, text in enumerate(normalized):
                if not text.strip():
                    vectors[index] = zero.copy()

        provider = self._get_provider()
        for start in range(0, len(non_empty), self.config.batch_size):
            batch = non_empty[start : start + self.config.batch_size]
            result = provider.embed_documents([text for _, text in batch])
            if len(result) != len(batch):
                raise ValueError("Embedding provider returned a different number of vectors")
            for (index, _), vector in zip(batch, result, strict=True):
                values = [float(value) for value in vector]
                if dimension is None:
                    dimension = len(values)
                if len(values) != dimension:
                    raise ValueError(f"Embedding dimension mismatch: expected {dimension}, got {len(values)}")
                vectors[index] = values

        if any(vector is None for vector in vectors):
            raise ValueError("Embedding provider returned incomplete results")
        return [vector for vector in vectors if vector is not None]

    def embed_query(self, text: str) -> list[float]:
        """Embed one query and enforce the configured index dimension."""
        if not text.strip():
            raise ValueError("Embedding query must not be empty")
        provider = self._get_provider()
        vector = [float(value) for value in provider.embed_query(text)]
        if self.config.dimensions is not None and len(vector) != self.config.dimensions:
            raise ValueError(f"Embedding dimension mismatch: expected {self.config.dimensions}, got {len(vector)}")
        return vector
