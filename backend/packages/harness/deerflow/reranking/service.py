from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from deerflow.config.reranker_config import RerankerConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RerankResult:
    ranked_indices: list[int]
    scores: list[float | None]
    degraded: bool = False
    error: str | None = None


class RerankerService:
    """Rerank candidate text while preserving every input on failure."""

    def __init__(self, config: RerankerConfig, *, transport: httpx.BaseTransport | None = None) -> None:
        if not config.enabled:
            raise ValueError("Reranker service is disabled; set reranker.enabled=true")
        if not config.base_url:
            raise ValueError("Reranker base_url is required")
        self.config = config
        self._transport = transport

    @property
    def _url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/{self.config.endpoint.lstrip('/')}"

    def _request_batch(self, client: httpx.Client, query: str, documents: list[str]) -> list[float]:
        last_error: Exception | None = None
        for _attempt in range(self.config.max_retries + 1):
            try:
                response = client.post(
                    self._url,
                    json={"model": self.config.model, "query": query, "documents": documents},
                )
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results") if isinstance(payload, dict) else None
                if not isinstance(results, list) or len(results) != len(documents):
                    raise ValueError("Reranker provider returned incomplete results")
                scores: list[float | None] = [None] * len(documents)
                for item in results:
                    if not isinstance(item, dict):
                        raise ValueError("Reranker provider returned an invalid result item")
                    index = item.get("index")
                    score = item.get("relevance_score", item.get("score"))
                    if not isinstance(index, int) or index < 0 or index >= len(documents) or scores[index] is not None:
                        raise ValueError("Reranker provider returned an invalid or duplicate index")
                    scores[index] = float(score)
                if any(score is None for score in scores):
                    raise ValueError("Reranker provider omitted candidate scores")
                return [score for score in scores if score is not None]
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def rerank(self, query: str, candidates: list[str]) -> RerankResult:
        if not candidates:
            return RerankResult(ranked_indices=[], scores=[])

        limited_count = min(len(candidates), self.config.candidate_limit)
        scored: list[tuple[int, float]] = []
        request_count = 0
        started = time.monotonic()
        headers = {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}

        try:
            with httpx.Client(headers=headers, timeout=self.config.timeout, transport=self._transport) as client:
                for start in range(0, limited_count, self.config.batch_size):
                    end = min(start + self.config.batch_size, limited_count)
                    batch_scores = self._request_batch(client, query, candidates[start:end])
                    request_count += 1
                    scored.extend((start + index, score) for index, score in enumerate(batch_scores))
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            if not self.config.fail_open:
                raise
            logger.warning("Reranker degraded to original order: model=%s candidates=%d error=%s", self.config.model, len(candidates), exc)
            return RerankResult(
                ranked_indices=list(range(len(candidates))),
                scores=[None] * len(candidates),
                degraded=True,
                error=str(exc),
            )

        ranked = sorted(scored, key=lambda item: (-item[1], item[0]))
        ranked_indices = [index for index, _score in ranked]
        scores: list[float | None] = [score for _index, score in ranked]
        if limited_count < len(candidates):
            ranked_indices.extend(range(limited_count, len(candidates)))
            scores.extend([None] * (len(candidates) - limited_count))

        logger.info(
            "Reranker completed: model=%s candidates=%d reranked=%d requests=%d duration_ms=%.1f",
            self.config.model,
            len(candidates),
            limited_count,
            request_count,
            (time.monotonic() - started) * 1000,
        )
        return RerankResult(ranked_indices=ranked_indices, scores=scores)

