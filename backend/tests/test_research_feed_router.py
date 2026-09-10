from __future__ import annotations

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import research_feed


def _topic_source(subject: str) -> tuple[dict[str, str | int], ...]:
    return (
        {
            "evidence_id": f"evidence-{subject}",
            "document_id": "document-local",
            "document_title": "木渎地方文献（测试）",
            "chunk_id": f"chunk-{subject}",
            "page_start": 1,
            "page_end": 2,
            "quote": f"文献记载：{subject}",
        },
    )


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
        self.metric_calls = 0
        self.seed_calls = 0

    async def get_active_release(self) -> research_feed.ActiveReleaseSnapshot | None:
        return self.release

    async def list_query_metrics(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int,
    ) -> tuple[research_feed.ResearchQueryMetric, ...]:
        self.metric_calls += 1
        assert start_at.tzinfo is not None
        assert end_at.tzinfo is not None
        return self.hot[:limit]

    async def list_release_topic_seeds(
        self,
        release_id: str,
        *,
        limit: int,
    ) -> tuple[research_feed.ResearchTopicSeed, ...]:
        self.seed_calls += 1
        assert self.release is not None
        assert release_id == self.release.id
        return self.seeds[:limit]


class FakeGrounder:
    def __init__(self, results: dict[str, research_feed.GroundingResult]) -> None:
        self.results = results
        self.queries: list[tuple[str, str, tuple[str, ...]]] = []

    async def ground(
        self,
        query: str,
        *,
        release_id: str,
        chunk_ids: tuple[str, ...] = (),
    ) -> research_feed.GroundingResult:
        self.queries.append((query, release_id, chunk_ids))
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
                sources=_topic_source("灵岩山"),
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

    assert [item.title for item in feed.items] == ["灵岩山为什么值得了解？"]
    assert feed.items[0].origin == "evidence_backed_fallback"
    assert feed.items[0].evidence_count == 4
    assert feed.items[0].retrieval_query == "灵岩山"
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
            research_feed.ResearchTopicSeed(query="木渎镇", subject="木渎镇", subject_type="place", sources=_topic_source("木渎镇")),
            research_feed.ResearchTopicSeed(query="灵岩山", subject="灵岩山", subject_type="place", sources=_topic_source("灵岩山")),
            research_feed.ResearchTopicSeed(query="胥江", subject="胥江", subject_type="waterway", sources=_topic_source("胥江")),
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

    service = research_feed.ResearchFeedService(repository, grounder)
    initial = await service.build_feed(
        date(2026, 8, 25),
        limit=2,
    )
    await service.wait_for_refreshes()
    feed = await service.build_feed(date(2026, 8, 25), limit=2)

    assert all(item.origin == "evidence_backed_fallback" for item in initial.items)
    assert [item.prompt for item in feed.items] == [
        "木渎镇有哪些寺庵记载？",
        "灵岩山有哪些方志记载？",
    ]
    assert [item.title for item in feed.items] == ["木渎镇为什么值得了解？", "灵岩山为什么值得了解？"]
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
        seeds=(research_feed.ResearchTopicSeed(query="香溪桥", subject="香溪桥", subject_type="bridge", sources=_topic_source("香溪桥")),),
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

    assert feed.items[0].title == "香溪桥有哪些历史故事？"
    assert feed.items[0].origin == "evidence_backed_fallback"


@pytest.mark.asyncio
async def test_document_fallback_uses_the_document_title_as_topic() -> None:
    repository = FakeCandidateRepository(
        seeds=(
            research_feed.ResearchTopicSeed(
                query="（同治）苏州府志",
                subject="（同治）苏州府志",
                subject_type="document",
                sources=_topic_source("同治苏州府志"),
            ),
        ),
    )
    grounder = FakeGrounder({"（同治）苏州府志": research_feed.GroundingResult(evidence_count=4, document_count=2)})

    feed = await research_feed.ResearchFeedService(repository, grounder).build_feed(
        date(2026, 8, 25),
        limit=1,
    )

    assert feed.items[0].title == "（同治）苏州府志记录了哪些木渎故事？"
    assert "内容线索" not in feed.items[0].title


@pytest.mark.asyncio
async def test_event_seed_uses_a_natural_question_without_changing_its_evidence() -> None:
    source = _topic_source("馆娃宫与西施叙事见于地方志汇录")
    repository = FakeCandidateRepository(
        seeds=(
            research_feed.ResearchTopicSeed(
                query="馆娃宫 西施",
                subject="馆娃宫与西施叙事见于地方志汇录",
                subject_type="event",
                summary="这是方志所汇录的历史记忆，不等同于已证实的精确年代事件。",
                place="灵岩山",
                people=("西施", "夫差"),
                sources=source,
            ),
        ),
    )

    feed = await research_feed.ResearchFeedService(
        repository,
        FakeGrounder(
            {
                "馆娃宫 西施": research_feed.GroundingResult(
                    evidence_count=1,
                    document_count=1,
                )
            }
        ),
    ).build_feed(date(2026, 8, 25), limit=1)

    item = feed.items[0]
    assert item.title == "馆娃宫和西施的故事在地方志中有哪些记载？"
    assert item.sources == source
    assert item.place == "灵岩山"
    assert item.people == ("西施", "夫差")


@pytest.mark.asyncio
async def test_source_bound_seed_is_rejected_when_its_bound_chunk_does_not_match() -> None:
    repository = FakeCandidateRepository(
        seeds=(
            research_feed.ResearchTopicSeed(
                query="朱买臣",
                subject="朱买臣",
                subject_type="person",
                sources=_topic_source("朱买臣"),
            ),
        ),
    )
    grounder = FakeGrounder({})

    feed = await research_feed.ResearchFeedService(repository, grounder).build_feed(
        date(2026, 8, 25),
        limit=1,
    )

    assert feed.items == ()
    assert grounder.queries == [
        ("朱买臣", "release-current", ("chunk-朱买臣",)),
    ]


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
        seeds=(research_feed.ResearchTopicSeed(query="木渎", subject="木渎", subject_type="place", sources=_topic_source("木渎")),),
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
        seeds=(research_feed.ResearchTopicSeed(query="灵岩山", subject="灵岩山", subject_type="place", sources=_topic_source("灵岩山")),),
    )
    service = research_feed.ResearchFeedService(
        repository,
        FakeGrounder({"灵岩山": research_feed.GroundingResult(evidence_count=4, document_count=2)}),
    )

    history = await service.build_history(date(2026, 8, 25), days=3, limit=1)

    assert history.current.generated_for == date(2026, 8, 25)
    assert [feed.generated_for for feed in history.previous] == [date(2026, 8, 24), date(2026, 8, 23)]
    assert all(feed.items[0].evidence_count >= 1 for feed in (history.current, *history.previous))


def test_daily_research_feed_endpoint_returns_grounded_selection(monkeypatch) -> None:
    service = research_feed.ResearchFeedService(
        FakeCandidateRepository(
            seeds=(research_feed.ResearchTopicSeed(query="灵岩山", subject="灵岩山", subject_type="place", sources=_topic_source("灵岩山")),),
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
    assert response.headers["x-research-feed-delivery"] == "seed"
    payload = response.json()
    assert payload["kind"] == "daily_grounded"
    assert payload["generated_for"] == "2026-08-25"
    assert payload["items"][0]["evidence_count"] == 4
    assert payload["next_refresh_at"].endswith("+08:00")

    with TestClient(app) as client:
        cached = client.get("/api/research-feed/daily?limit=6")
        invalid_limit = client.get("/api/research-feed/daily?limit=3")

    assert cached.headers["x-research-feed-delivery"] == "cache"
    assert invalid_limit.status_code == 422


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


@pytest.mark.asyncio
async def test_evidence_seed_becomes_public_topic_with_source_binding_and_is_cached() -> None:
    seed = research_feed.ResearchTopicSeed(
        query="灵岩山",
        subject="灵岩山",
        subject_type="place",
        summary="吴地地方文献中的山名与寺观记载。",
        dynasty="宋朝",
        time_label="约宋朝",
        place="灵岩山",
        entities=({"id": "place-lingyan", "name": "灵岩山", "entity_type": "place"},),
        sources=(
            {
                "evidence_id": "evidence-1",
                "document_id": "document-1",
                "document_title": "（康熙）吳縣志",
                "chunk_id": "chunk-1",
                "page_start": 123,
                "page_end": 126,
                "quote": "灵岩山旧志记载。",
            },
            {
                "evidence_id": "evidence-2",
                "document_id": "document-1",
                "document_title": "（康熙）吳縣志",
                "chunk_id": "chunk-2",
                "page_start": 127,
                "page_end": 130,
                "quote": "灵岩山寺观记载。",
            },
        ),
    )
    repository = FakeCandidateRepository(seeds=(seed,))
    service = research_feed.ResearchFeedService(
        repository,
        FakeGrounder(
            {
                "灵岩山": research_feed.GroundingResult(
                    evidence_count=2,
                    document_count=1,
                )
            }
        ),
    )

    first = await service.build_feed(date(2026, 8, 25), limit=1)
    second = await service.build_feed(date(2026, 8, 25), limit=1)

    assert first is second
    assert first.items[0].title == "灵岩山为什么值得了解？"
    assert first.items[0].sources[0]["chunk_id"] == "chunk-1"
    assert first.items[0].entities[0]["id"] == "place-lingyan"
    assert first.notice == "部分内容暂时使用本地资料"
    assert repository.seed_calls == 1


@pytest.mark.asyncio
async def test_uncached_feed_returns_verified_seeds_without_waiting_for_hot_refresh() -> None:
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    class SlowMetricsRepository(FakeCandidateRepository):
        async def list_query_metrics(
            self,
            *,
            start_at: datetime,
            end_at: datetime,
            limit: int,
        ) -> tuple[research_feed.ResearchQueryMetric, ...]:
            refresh_started.set()
            await release_refresh.wait()
            return ()

    repository = SlowMetricsRepository(
        seeds=(
            research_feed.ResearchTopicSeed(
                query="灵岩山",
                subject="灵岩山",
                subject_type="place",
                sources=_topic_source("灵岩山"),
            ),
        ),
    )
    service = research_feed.ResearchFeedService(
        repository,
        FakeGrounder(
            {
                "灵岩山": research_feed.GroundingResult(
                    evidence_count=1,
                    document_count=1,
                )
            }
        ),
    )

    feed = await asyncio.wait_for(
        service.build_feed(date(2026, 8, 25), limit=1),
        timeout=0.2,
    )

    assert feed.items[0].title == "灵岩山为什么值得了解？"
    await asyncio.wait_for(refresh_started.wait(), timeout=0.2)
    release_refresh.set()
    await service.wait_for_refreshes()


@pytest.mark.asyncio
async def test_candidate_failure_reuses_last_verified_seed_pool() -> None:
    class FailingSeedRepository(FakeCandidateRepository):
        fail = False

        async def list_release_topic_seeds(
            self,
            release_id: str,
            *,
            limit: int,
        ) -> tuple[research_feed.ResearchTopicSeed, ...]:
            if self.fail:
                raise RuntimeError("database unavailable")
            return await super().list_release_topic_seeds(release_id, limit=limit)

    repository = FailingSeedRepository(
        seeds=(
            research_feed.ResearchTopicSeed(
                query="范仲淹",
                subject="范仲淹",
                subject_type="person",
                sources=_topic_source("范仲淹"),
            ),
        ),
    )
    service = research_feed.ResearchFeedService(
        repository,
        FakeGrounder(
            {
                "范仲淹": research_feed.GroundingResult(
                    evidence_count=1,
                    document_count=1,
                )
            }
        ),
    )
    await service.build_feed(date(2026, 8, 25), limit=1)
    await service.wait_for_refreshes()
    repository.fail = True

    feed = await service.build_feed(date(2026, 8, 26), limit=1)

    assert feed.items[0].title == "地方文献怎样记载范仲淹与吴地的联系？"
    assert feed.notice == "今日内容更新暂时失败，当前展示本地精选话题"
