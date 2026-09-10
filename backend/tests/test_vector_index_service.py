from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from wu_culture.vectors import (
    VectorBuildItem,
    VectorIndexConflict,
    VectorIndexState,
    VectorIndexStatus,
    VectorIndexVersion,
    VectorSearchRequest,
    VectorSearchResponse,
)

from deerflow.config.embedding_config import EmbeddingConfig
from deerflow.embeddings import EmbeddingService, VectorEmbeddingError, VectorIndexService

NOW = datetime(2026, 7, 21, 22, 0, tzinfo=UTC)


class _Embeddings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def embed_documents(self, texts):
        return [[1.0 if text == "木渎" else 2.0, 0.0] for text in texts]

    def embed_query(self, _text):
        return [1.0, 0.0]


class _FailingEmbeddings(_Embeddings):
    def embed_documents(self, texts):
        raise RuntimeError("provider unavailable")


class _Repository:
    def __init__(self) -> None:
        self.versions = []
        self.vectors = ()

    async def get_release_build_items(self, release_id):
        assert release_id == "release-1"
        return "a" * 64, (
            VectorBuildItem(chunk_id="chunk-1", text="木渎"),
            VectorBuildItem(chunk_id="chunk-2", text="香溪"),
        )

    async def create_build(self, version, *, expected_state_version):
        assert expected_state_version == 0
        self.versions.append(version)
        return version

    async def complete_build(self, version, vectors):
        self.versions.append(version)
        self.vectors = vectors
        return version

    async def fail_build(self, version):
        self.versions.append(version)
        return version

    async def resolve_search_version(self, release_id):
        assert release_id is None
        return self.versions[-1]

    async def search_by_vector(self, request, query_vector):
        assert query_vector == (1.0, 0.0)
        return VectorSearchResponse(
            query=request.query,
            release_id="release-1",
            index_id=self.versions[-1].id,
            embedding_model="test-embedding",
            embedding_version="v1",
            hits=(),
        )

    async def get_state(self, release_id):
        return VectorIndexState(release_id=release_id, state_version=0)


def _service(repository, *, version="v1", embeddings_factory=_Embeddings):
    embeddings = EmbeddingService(
        EmbeddingConfig(
            enabled=True,
            model="test-embedding",
            version=version,
            dimensions=2,
            batch_size=1,
        ),
        embeddings_factory=embeddings_factory,
    )
    return VectorIndexService(repository, embeddings)


def test_rebuild_batches_all_chunks_then_searches_with_same_embedding_identity() -> None:
    asyncio.run(_exercise_rebuild_and_search())


async def _exercise_rebuild_and_search() -> None:
    repository = _Repository()
    service = _service(repository)

    ready = await service.rebuild(
        "release-1",
        expected_state_version=0,
        actor_id="admin-1",
        started_at=NOW,
    )

    assert ready.status is VectorIndexStatus.READY
    assert ready.item_count == 2
    assert repository.vectors == (("chunk-1", (1.0, 0.0)), ("chunk-2", (2.0, 0.0)))
    response = await service.search(VectorSearchRequest(query="旧桥"))
    assert response.index_id == ready.id


def test_search_rejects_changed_embedding_version_before_generating_query_vector() -> None:
    async def exercise() -> None:
        repository = _Repository()
        repository.versions.append(
            VectorIndexVersion(
                id="vector-old",
                release_id="release-1",
                release_manifest_sha256="a" * 64,
                embedding_model="test-embedding",
                embedding_version="v1",
                dimensions=2,
                status=VectorIndexStatus.READY,
                item_count=2,
                created_by="admin-1",
                created_at=NOW,
                completed_at=NOW,
            )
        )

        with pytest.raises(VectorIndexConflict, match="different embedding"):
            await _service(repository, version="v2").search(VectorSearchRequest(query="旧桥"))

    asyncio.run(exercise())


def test_failed_provider_marks_build_failed_without_completing_it() -> None:
    async def exercise() -> None:
        repository = _Repository()
        with pytest.raises(VectorEmbeddingError, match="provider unavailable"):
            await _service(repository, embeddings_factory=_FailingEmbeddings).rebuild(
                "release-1",
                expected_state_version=0,
                actor_id="admin-1",
                started_at=NOW,
            )
        assert [version.status for version in repository.versions] == [
            VectorIndexStatus.BUILDING,
            VectorIndexStatus.FAILED,
        ]

    asyncio.run(exercise())
