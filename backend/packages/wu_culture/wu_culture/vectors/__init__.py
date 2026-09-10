"""Versioned vector index lifecycle and semantic search contracts."""

from .service import (
    VectorBuildItem,
    VectorIndexBuildRequest,
    VectorIndexConflict,
    VectorIndexError,
    VectorIndexNotReady,
    VectorIndexRepository,
    VectorIndexState,
    VectorIndexStatus,
    VectorIndexVersion,
    VectorSearchHit,
    VectorSearchRequest,
    VectorSearchResponse,
    begin_vector_index,
    complete_vector_index,
    fail_vector_index,
)

__all__ = [
    "VectorBuildItem",
    "VectorIndexBuildRequest",
    "VectorIndexConflict",
    "VectorIndexError",
    "VectorIndexNotReady",
    "VectorIndexRepository",
    "VectorIndexState",
    "VectorIndexStatus",
    "VectorIndexVersion",
    "VectorSearchHit",
    "VectorSearchRequest",
    "VectorSearchResponse",
    "begin_vector_index",
    "complete_vector_index",
    "fail_vector_index",
]
