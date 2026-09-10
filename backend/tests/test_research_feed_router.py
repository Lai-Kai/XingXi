from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import research_feed


class FakeCandidateRepository:
    def __init__(
        self,
        *,
        hot: tuple[research_feed.ResearchQueryMetric, ...] = (),
        seeds: tuple[research_feed.ResearchTopicSeed, ...] = (),
        release: research_feed.ActiveReleaseSnapshot | None = None,
    ) -> None:
        self.hot = hot
        self.seeds = seeds
        self.release = release or research_feed.ActiveReleaseSnapshot(
            id="release-current",
            version="v7",
        )

    async def get_active_release(self) -> research_feed.ActiveReleaseSnapshot | None:
        return self.release

    async def list_query_metrics(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int,
    ) -> tuple[research_feed.ResearchQueryMetric, ...]:
        assert start_at.tzinfo is not None
        assert end_at.tzinfo is not None
        return self.hot[:limit]

    async def list_release_topic_seeds(
        self,
        release_id: str,
        *,
        limit: int,
    ) -> tuple[research_feed.ResearchTopicSeed, ...]:
        assert self.release is not None
        assert release_id == self.release.id
        return self.seeds[:limit]


class FakeGrounder:
    def __init__(self, results: dict[str, research_feed.GroundingResult]) -> None:
        self.results = results
        self.queries: list[tuple[str, str]] = []

    async def ground(self, query: str, *, release_id: str) -> research_feed.GroundingResult:
        self.queries.append((query, release_id))
        return self.results.get(
            query,
            research_feed.GroundingResult(evidence_count=0, document_count=0),
        )


@pytest.mark.asyncio
async def test_zero_evidence_hot_query_is_rejected_and_grounded_fallback_is_used() -> None:
    repository = FakeCandidateRepository(
        hot=(
            research_feed.ResearchQueryMetric(
                query="核验严家花园的营建年代，比较不同文献的证据与分歧。",
                user_count=8,
                search_count=12,
            ),
        ),
        seeds=(
            research_feed.ResearchTopicSeed(
                query="灵岩山",
                subject="灵岩山",
                subject_type="place",
            ),
        ),
    )
    grounder = FakeGrounder(
        {
            "严家花园 营建年代": research_feed.GroundingResult(
                evidence_count=0,
                document_count=0,
            ),
            "灵岩山": research_feed.GroundingResult(
                evidence_count=4,
                document_count=2,
            ),
        }
    )

    feed = await research_feed.ResearchFeedService(repository, grounder).build_feed(
        date(2026, 8, 25),
        limit=1,
    )

    assert [item.title for item in feed.items] == ["灵岩山"]
    assert feed.items[0].origin == "evidence_backed_fallback"
    assert feed.items[0].evidence_count == 4
    assert feed.items[0].knowledge_release_id == "release-current"
    assert all("严家花园" not in item.title for item in feed.items)


@pytest.mark.asyncio
async def test_yesterday_hot_topics_rank_by_unique_users_then_searches() -> None:
    repository = FakeCandidateRepository(
        hot=(
            research_feed.ResearchQueryMetric(query="胥江的历史河道如何变化？", user_count=2, search_count=9),
            research_feed.ResearchQueryMetric(query="灵岩山有哪些方志记载？", user_count=4, search_count=4),
            research_feed.ResearchQueryMetric(query="木渎镇有哪些寺庵记载？", user_count=4, search_count=7),
        ),
        seeds=(
            research_feed.ResearchTopicSeed(query="木渎镇", subject="木渎镇", subject_type="place"),
            research_feed.ResearchTopicSeed(query="灵岩山", subject="灵岩山", subject_type="place"),
            research_feed.ResearchTopicSeed(query="胥江", subject="胥江", subject_type="waterway"),
        ),
    )
    grounder = FakeGrounder(
        {
            "木渎镇": research_feed.GroundingResult(evidence_count=3, document_count=2),
            "灵岩山": research_feed.GroundingResult(evidence_count=3, document_count=2),
            "胥江": research_feed.GroundingResult(evidence_count=3, document_count=2),
            "胥江 历史河道 变化": research_feed.GroundingResult(evidence_count=3, document_count=2),
            "灵岩山 方志记载": research_feed.GroundingResult(evidence_count=3, document_count=2),
            "木渎镇 寺庵记载": research_feed.GroundingResult(evidence_count=3, document_count=2),
        }
    )

    feed = await research_feed.ResearchFeedService(repository, grounder).build_feed(
        date(2026, 8, 25),
        limit=2,
    )

    assert [item.prompt for item in feed.items] == [
        "木渎镇有哪些寺庵记载？",
        "灵岩山有哪些方志记载？",
    ]
    assert [item.title for item in feed.items] == ["木渎镇", "灵岩山"]
    assert [item.popularity_users for item in feed.items] == [4, 4]
    assert all(item.origin == "yesterday_hot" for item in feed.items)


@pytest.mark.asyncio
async def test_hot_query_without_a_source_topic_is_rejected() -> None:
    repository = FakeCandidateRepository(
        hot=(
            research_feed.ResearchQueryMetric(
                query="古桥的修缮历史记录？",
                user_count=8,
                search_count=12,
            ),
        ),
        seeds=(research_feed.ResearchTopicSeed(query="香溪桥", subject="香溪桥", subject_type="bridge"),),
    )
    grounder = FakeGrounder(
        {
            "古桥 修缮历史记录": research_feed.GroundingResult(evidence_count=3, document_count=2),
            "香溪桥": research_feed.GroundingResult(evidence_count=3, document_count=2),
        }
    )

    feed = await research_feed.ResearchFeedService(repository, grounder).build_feed(
        date(2026, 8, 25),
        limit=1,
    )

    assert feed.items[0].title == "香溪桥"
    assert feed.items[0].origin == "evidence_backed_fallback"


@pytest.mark.asyncio
async def test_document_fallback_uses_the_document_title_as_topic() -> None:
    repository = FakeCandidateRepository(
        seeds=(
            research_feed.ResearchTopicSeed(
                query="（同治）苏州府志",
                subject="（同治）苏州府志",
                subject_type="document",
            ),
        ),
    )
    grounder = FakeGrounder({"（同治）苏州府志": research_feed.GroundingResult(evidence_count=4, document_count=2)})

    feed = await research_feed.ResearchFeedService(repository, grounder).build_feed(
        date(2026, 8, 25),
        limit=1,
    )

    assert feed.items[0].title == "（同治）苏州府志"
    assert "内容线索" not in feed.items[0].title


@pytest.mark.asyncio
async def test_procedural_test_prompts_are_not_published_as_hot_topics() -> None:
    repository = FakeCandidateRepository(
        hot=(
            research_feed.ResearchQueryMetric(
                query='这是工具调用验收，必须调用 search_sources(query="木渎镇")。',
                user_count=20,
                search_count=30,
            ),
        ),
        seeds=(research_feed.ResearchTopicSeed(query="木渎", subject="木渎", subject_type="place"),),
    )
    grounder = FakeGrounder({"木渎": research_feed.GroundingResult(evidence_count=6, document_count=3)})

    feed = await research_feed.ResearchFeedService(repository, grounder).build_feed(
        date(2026, 8, 25),
        limit=1,
    )

    assert feed.items[0].origin == "evidence_backed_fallback"
    assert "search_sources" not in feed.items[0].prompt


@pytest.mark.asyncio
async def test_no_active_release_or_no_grounded_candidate_returns_empty_feed() -> None:
    no_release = FakeCandidateRepository()
    no_release.release = None
    empty = await research_feed.ResearchFeedService(no_release, FakeGrounder({})).build_feed(
        date(2026, 8, 25),
        limit=2,
    )
    assert empty.items == ()

    ungrounded = FakeCandidateRepository(
        hot=(research_feed.ResearchQueryMetric(query="不存在的题目", user_count=3, search_count=3),),
        seeds=(research_feed.ResearchTopicSeed(query="也不存在", subject="也不存在", subject_type="place"),),
    )
    feed = await research_feed.ResearchFeedService(ungrounded, FakeGrounder({})).build_feed(
        date(2026, 8, 25),
        limit=2,
    )
    assert feed.items == ()


@pytest.mark.asyncio
async def test_history_uses_the_same_grounding_gate_for_each_day() -> None:
    repository = FakeCandidateRepository(
        seeds=(research_feed.ResearchTopicSeed(query="灵岩山", subject="灵岩山", subject_type="place"),),
    )
    service = research_feed.ResearchFeedService(
        repository,
        FakeGrounder({"灵岩山": research_feed.GroundingResult(evidence_count=4, document_count=2)}),
    )

    history = await service.build_history(date(2026, 8, 25), days=3, limit=1)

    assert history.current.generated_for == date(2026, 8, 25)
    assert [feed.generated_for for feed in history.previous] == [date(2026, 8, 24), date(2026, 8, 23)]
    assert all(feed.items[0].evidence_count >= 2 for feed in (history.current, *history.previous))


def test_daily_research_feed_endpoint_returns_grounded_selection(monkeypatch) -> None:
    service = research_feed.ResearchFeedService(
        FakeCandidateRepository(
            seeds=(research_feed.ResearchTopicSeed(query="灵岩山", subject="灵岩山", subject_type="place"),),
        ),
        FakeGrounder({"灵岩山": research_feed.GroundingResult(evidence_count=4, document_count=2)}),
    )
    fixed_now = datetime(2026, 8, 25, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr(research_feed, "_now_shanghai", lambda: fixed_now)
    app = FastAPI()
    app.include_router(research_feed.router)
    app.dependency_overrides[research_feed.get_research_feed_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/api/research-feed/daily")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["kind"] == "daily_grounded"
    assert payload["generated_for"] == "2026-08-25"
    assert payload["items"][0]["evidence_count"] == 4
    assert payload["next_refresh_at"].endswith("+08:00")


def test_history_endpoint_validates_range(monkeypatch) -> None:
    service = research_feed.ResearchFeedService(FakeCandidateRepository(), FakeGrounder({}))
    monkeypatch.setattr(
        research_feed,
        "_now_shanghai",
        lambda: datetime(2026, 8, 25, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    app = FastAPI()
    app.include_router(research_feed.router)
    app.dependency_overrides[research_feed.get_research_feed_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/api/research-feed/history", params={"days": 3})
        invalid = client.get("/api/research-feed/history", params={"days": 31})

    assert response.status_code == 200
    assert response.json()["history_days"] == 3
    assert len(response.json()["previous"]) == 2
    assert invalid.status_code == 422
