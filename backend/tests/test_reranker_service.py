import httpx
import pytest

from deerflow.config.reranker_config import RerankerConfig
from deerflow.reranking import RerankerService


def _service(handler, **overrides):
    config = RerankerConfig(
        enabled=True,
        model="test-reranker",
        api_key="test-key",
        base_url="https://reranker.example/v1",
        **overrides,
    )
    transport = httpx.MockTransport(handler)
    return RerankerService(config, transport=transport)


def test_reranker_orders_candidates_by_provider_score():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url == "https://reranker.example/v1/rerank"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.2},
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 2, "relevance_score": 0.5},
                ]
            },
        )

    result = _service(handler).rerank("木渎古桥", ["甲", "乙", "丙"])

    assert result.ranked_indices == [1, 2, 0]
    assert result.scores == [0.9, 0.5, 0.2]
    assert result.degraded is False


def test_reranker_batches_candidates_and_keeps_global_indices():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        calls.append(payload["documents"])
        scores = [float(len(text)) for text in payload["documents"]]
        return httpx.Response(200, json={"results": [{"index": i, "relevance_score": score} for i, score in enumerate(scores)]})

    result = _service(handler, batch_size=2).rerank("问题", ["a", "bbbb", "cc", "ddd"])

    assert calls == [["a", "bbbb"], ["cc", "ddd"]]
    assert result.ranked_indices == [1, 3, 2, 0]


def test_reranker_appends_candidates_beyond_configured_limit():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": 0.8}]})

    result = _service(handler, candidate_limit=2).rerank("问题", ["a", "b", "c", "d"])

    assert result.ranked_indices == [1, 0, 2, 3]
    assert result.scores == [0.8, 0.1, None, None]


def test_reranker_retries_then_degrades_without_losing_candidates():
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "unavailable"})

    result = _service(handler, max_retries=2).rerank("问题", ["a", "b", "c"])

    assert attempts == 3
    assert result.ranked_indices == [0, 1, 2]
    assert result.scores == [None, None, None]
    assert result.degraded is True
    assert "503" in (result.error or "")


def test_reranker_can_fail_closed_when_configured():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    service = _service(handler, max_retries=0, fail_open=False)

    with pytest.raises(httpx.ReadTimeout):
        service.rerank("问题", ["a"])


def test_reranker_requires_explicit_enablement():
    with pytest.raises(ValueError, match="disabled"):
        RerankerService(RerankerConfig())
