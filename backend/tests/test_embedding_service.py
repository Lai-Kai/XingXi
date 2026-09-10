import pytest

from deerflow.config.embedding_config import EmbeddingConfig
from deerflow.embeddings import EmbeddingService


class FakeEmbeddings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0]


def test_embedding_service_batches_and_preserves_empty_text():
    service = EmbeddingService(
        EmbeddingConfig(enabled=True, dimensions=2, batch_size=1),
        embeddings_factory=FakeEmbeddings,
    )

    vectors = service.embed_documents(["木渎", "  ", "香溪"])

    assert vectors == [[2.0, 1.0], [0.0, 0.0], [2.0, 1.0]]
    assert service._provider.kwargs["timeout"] == 60.0
    assert service._provider.kwargs["max_retries"] == 2


def test_embedding_service_rejects_dimension_mismatch():
    class WrongDimension(FakeEmbeddings):
        def embed_documents(self, texts):
            return [[1.0, 2.0, 3.0] for _ in texts]

    service = EmbeddingService(
        EmbeddingConfig(enabled=True, dimensions=2),
        embeddings_factory=WrongDimension,
    )

    with pytest.raises(ValueError, match="dimension mismatch"):
        service.embed_documents(["木渎"])


def test_embedding_service_requires_explicit_enablement():
    with pytest.raises(ValueError, match="disabled"):
        EmbeddingService(EmbeddingConfig())


def test_embedding_service_embeds_query_and_checks_dimension():
    service = EmbeddingService(
        EmbeddingConfig(enabled=True, dimensions=2),
        embeddings_factory=FakeEmbeddings,
    )

    assert service.embed_query("木渎") == [2.0, 1.0]

    with pytest.raises(ValueError, match="must not be empty"):
        service.embed_query("  ")
