from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from wu_culture.vectors import (
    VectorIndexStatus,
    VectorSearchRequest,
    begin_vector_index,
    complete_vector_index,
    fail_vector_index,
)

from deerflow.config.embedding_config import EmbeddingConfig

NOW = datetime(2026, 7, 21, 20, 0, tzinfo=UTC)


def test_embedding_config_has_explicit_version_identity() -> None:
    config = EmbeddingConfig(enabled=True, model="embedding-model", version="mudu-v1", dimensions=3)

    assert config.identity == "embedding-model:mudu-v1:3"
    with pytest.raises(ValidationError):
        EmbeddingConfig(enabled=True, model="embedding-model", version="", dimensions=3)


def test_vector_index_lifecycle_is_immutable_and_versioned() -> None:
    building = begin_vector_index(
        index_id="vector-index-1",
        release_id="release-1",
        release_manifest_sha256="a" * 64,
        embedding_model="embedding-model",
        embedding_version="mudu-v1",
        dimensions=3,
        created_by="admin-1",
        created_at=NOW,
    )
    ready = complete_vector_index(building, item_count=2, completed_at=NOW)

    assert building.status is VectorIndexStatus.BUILDING
    assert ready.status is VectorIndexStatus.READY
    assert ready.item_count == 2
    assert building.status is VectorIndexStatus.BUILDING


def test_failed_index_keeps_structured_error() -> None:
    building = begin_vector_index(
        index_id="vector-index-1",
        release_id="release-1",
        release_manifest_sha256="a" * 64,
        embedding_model="embedding-model",
        embedding_version="mudu-v1",
        dimensions=3,
        created_by="admin-1",
        created_at=NOW,
    )
    failed = fail_vector_index(building, error_code="provider_unavailable", error_message="embedding endpoint returned 503", failed_at=NOW)

    assert failed.status is VectorIndexStatus.FAILED
    assert failed.error_code == "provider_unavailable"


def test_vector_search_request_bounds_similarity_and_top_k() -> None:
    request = VectorSearchRequest(query="溪流旁的旧桥", top_k=10, min_similarity=0.35)

    assert request.top_k == 10
    with pytest.raises(ValidationError):
        VectorSearchRequest(query="溪流旁的旧桥", top_k=101)
    with pytest.raises(ValidationError):
        VectorSearchRequest(query="溪流旁的旧桥", min_similarity=1.1)
    with pytest.raises(ValidationError, match="duplicate document"):
        VectorSearchRequest(query="溪流旁的旧桥", document_ids=("document-1", "document-1"))
