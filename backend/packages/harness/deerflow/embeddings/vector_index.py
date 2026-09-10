from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from wu_culture.vectors import (
    VectorIndexConflict,
    VectorIndexVersion,
    VectorSearchRequest,
    VectorSearchResponse,
    begin_vector_index,
    complete_vector_index,
    fail_vector_index,
)

from deerflow.embeddings.service import EmbeddingService


class VectorEmbeddingError(RuntimeError):
    """Raised when the configured embedding provider cannot serve an index operation."""


class VectorIndexService:
    """Coordinate provider calls without exposing a partially built index."""

    def __init__(self, repository, embeddings: EmbeddingService) -> None:  # noqa: ANN001
        self._repository = repository
        self._embeddings = embeddings

    async def rebuild(
        self,
        release_id: str,
        *,
        expected_state_version: int,
        actor_id: str,
        started_at: datetime,
    ) -> VectorIndexVersion:
        dimensions = self._embeddings.config.dimensions
        if dimensions is None:
            raise ValueError("embedding.dimensions must be configured before building a persistent vector index")
        manifest_sha256, items = await self._repository.get_release_build_items(release_id)
        if not items:
            raise VectorIndexConflict("knowledge release has no text chunks to embed")
        building = begin_vector_index(
            index_id=f"vector-{uuid4()}",
            release_id=release_id,
            release_manifest_sha256=manifest_sha256,
            embedding_model=self._embeddings.config.model,
            embedding_version=self._embeddings.config.version,
            dimensions=dimensions,
            created_by=actor_id,
            created_at=started_at,
        )
        await self._repository.create_build(building, expected_state_version=expected_state_version)
        try:
            embedded = await asyncio.to_thread(
                self._embeddings.embed_documents,
                [item.text for item in items],
            )
            vectors = tuple((item.chunk_id, tuple(vector)) for item, vector in zip(items, embedded, strict=True))
            ready = complete_vector_index(
                building,
                item_count=len(vectors),
                completed_at=datetime.now(started_at.tzinfo),
            )
            return await self._repository.complete_build(ready, vectors)
        except Exception as exc:
            failed = fail_vector_index(
                building,
                error_code=type(exc).__name__,
                error_message=str(exc)[:4000],
                failed_at=datetime.now(started_at.tzinfo),
            )
            await self._repository.fail_build(failed)
            if isinstance(exc, VectorIndexConflict):
                raise
            raise VectorEmbeddingError(f"embedding index build failed: {exc}") from exc

    async def search(self, request: VectorSearchRequest) -> VectorSearchResponse:
        version = await self._repository.resolve_search_version(request.release_id)
        config = self._embeddings.config
        if version.embedding_model != config.model or version.embedding_version != config.version or config.dimensions != version.dimensions:
            raise VectorIndexConflict("active vector index uses a different embedding model, version, or dimension; rebuild it before searching")
        try:
            query_vector = await asyncio.to_thread(self._embeddings.embed_query, request.query)
        except Exception as exc:
            raise VectorEmbeddingError(f"embedding query failed: {exc}") from exc
        return await self._repository.search_by_vector(request, tuple(query_vector))
