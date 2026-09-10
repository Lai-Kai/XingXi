"""Evidence-gated daily research topics for the Xingxi workspace."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import load_only
from wu_culture import AuthorizedUse, evaluate_source_access
from wu_culture.fulltext import parse_fulltext_query

from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.wu_culture.knowledge_seed import seed_evidence_chunk_id as _seed_evidence_chunk_id

router = APIRouter(prefix="/api/research-feed", tags=["research-feed"])

logger = logging.getLogger(__name__)
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_MIN_EVIDENCE_COUNT = 1
_HOT_QUERY_LIMIT = 24
_FALLBACK_SEED_LIMIT = 64
_PROCEDURAL_MARKERS = (
    "search_sources",
    "evidence://",
    "工具调用",
    "tool call",
    "参数必须",
    "第一个动作",
)
_COMPARISON_MARKERS = ("比较", "对读", "分歧", "异同", "不同文献", "不同来源")
_LOCAL_KNOWLEDGE_SEED_PATH = Path(__file__).resolve().parents[3] / "data" / "fuxianzhi_knowledge_seed.json"


class DailyResearchItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    summary: str
    tag: str
    source_basis: str
    prompt: str
    retrieval_query: str
    origin: Literal["yesterday_hot", "evidence_backed_fallback"]
    evidence_count: int = Field(ge=_MIN_EVIDENCE_COUNT)
    knowledge_release_id: str
    popularity_users: int | None = Field(default=None, ge=1)
    popularity_searches: int | None = Field(default=None, ge=1)
    dynasty: str | None = None
    time_label: str = "年代待考"
    place: str | None = None
    people: tuple[str, ...] = ()
    entities: tuple[dict[str, str], ...] = ()
    sources: tuple[dict[str, str | int | None], ...] = ()
    degraded: bool = False
    notice: str | None = None


class DailyResearchFeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["daily_grounded"] = "daily_grounded"
    generated_for: date
    next_refresh_at: datetime
    items: tuple[DailyResearchItem, ...]
    notice: str | None = None


class DailyResearchHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["daily_grounded_history"] = "daily_grounded_history"
    current: DailyResearchFeed
    previous: tuple[DailyResearchFeed, ...]
    history_days: int = Field(ge=1, le=30)


class ActiveReleaseSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: str


class ResearchQueryMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    user_count: int = Field(ge=1)
    search_count: int = Field(ge=1)


class ResearchTopicSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    subject: str
    subject_type: str
    summary: str | None = None
    dynasty: str | None = None
    time_label: str = "年代待考"
    place: str | None = None
    people: tuple[str, ...] = ()
    entities: tuple[dict[str, str], ...] = ()
    sources: tuple[dict[str, str | int | None], ...] = ()


class GroundingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_count: int = Field(ge=0)
    document_count: int = Field(ge=0)


class ResearchFeedCandidateRepository(Protocol):
    async def get_active_release(self) -> ActiveReleaseSnapshot | None: ...

    async def list_query_metrics(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int,
    ) -> tuple[ResearchQueryMetric, ...]: ...

    async def list_release_topic_seeds(
        self,
        release_id: str,
        *,
        limit: int,
    ) -> tuple[ResearchTopicSeed, ...]: ...


class ResearchTopicGrounder(Protocol):
    async def ground(
        self,
        query: str,
        *,
        release_id: str,
        chunk_ids: tuple[str, ...] = (),
    ) -> GroundingResult: ...


def _now_shanghai() -> datetime:
    return datetime.now(_SHANGHAI)


def _normalize_query(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _metric_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", _normalize_query(value)).casefold()
    return re.sub(r"[\s，。！？、；：,.!?;:'\"“”‘’（）()《》]+", "", normalized)


def _is_publishable_hot_query(value: str) -> bool:
    normalized = _normalize_query(value)
    if not 4 <= len(normalized) <= 180:
        return False
    lowered = normalized.casefold()
    return not any(marker.casefold() in lowered for marker in _PROCEDURAL_MARKERS)


def _retrieval_query(value: str) -> str:
    normalized = _normalize_query(value)
    normalized = re.sub(r"^(请|请问|请检索|检索|研究|考证|核验|梳理|整理)+", "", normalized)
    normalized = re.sub(r"比较不同(文献|来源)的证据与分歧", "", normalized)
    normalized = normalized.replace("有哪些", " ").replace("如何", " ").replace("的", " ")
    normalized = re.sub(r"[，。！？、；：,.!?;:'\"“”‘’（）()《》]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _stable_id(release_id: str, origin: str, prompt: str) -> str:
    digest = hashlib.sha256(f"{release_id}\0{origin}\0{prompt}".encode()).hexdigest()[:16]
    return f"research-{digest}"


def _next_refresh(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=_SHANGHAI)


def _fallback_copy(seed: ResearchTopicSeed) -> tuple[str, str, str, str]:
    topic = _normalize_query(seed.subject)
    templates = {
        "person": (
            f"{topic}与吴地有什么联系？",
            f"从当前已发布方志证据中了解{topic}的生平、活动地点和相关事件。",
            "人物考证",
            f"用通俗方式介绍{topic}与吴地的联系，逐条引用本地资料出处。",
        ),
        "place": (
            f"{topic}为什么值得了解？",
            f"从当前已发布文献中了解{topic}的名称、沿革与相关历史事件。",
            "历史地理",
            f"用通俗方式介绍{topic}的历史沿革与方志记载，区分明确记载与后世推断。",
        ),
        "waterway": (
            f"{topic}在地方文献中有哪些记载？",
            f"依据当前已发布文献了解{topic}的名称、河道关系与历代变化。",
            "水系考证",
            f"用通俗方式介绍{topic}的历史沿革，并列出可核验的方志证据。",
        ),
        "bridge": (
            f"{topic}有哪些历史故事？",
            f"从当前已发布文献中了解{topic}的名称、位置和历次修建记载。",
            "古迹考证",
            f"用通俗方式介绍{topic}的名称、位置与重修记录，并标明证据出处。",
        ),
        "building": (
            f"{topic}经历过哪些变化？",
            f"从当前已发布方志材料中了解{topic}的建置、修缮和功能变化。",
            "建筑史",
            f"用通俗方式介绍{topic}的建置与沿革，并逐条列出方志依据。",
        ),
        "garden": (
            f"{topic}有哪些值得看的历史？",
            f"从当前已发布材料中了解{topic}的始建、扩建和修缮年代。",
            "园林史",
            f"用通俗方式介绍{topic}的营建与修缮记录，并引用本地资料。",
        ),
        "event": (
            f"{topic}发生了什么？",
            f"依据当前已发布史料了解{topic}的时间、地点、人物和后续影响。",
            "历史事件",
            f"用通俗方式介绍{topic}的时间、地点与影响，并列出可核验出处。",
        ),
        "document": (
            f"{topic}记录了哪些木渎故事？",
            f"从当前已发布索引中了解{topic}的版本、卷目和可检索内容。",
            "方志版本",
            f"用通俗方式介绍{topic}记录的地方故事，并引用当前知识库中的原文位置。",
        ),
    }
    return templates.get(seed.subject_type, templates["place"])


def _public_topic_copy(seed: ResearchTopicSeed) -> tuple[str, str, str, str]:
    """Turn an evidence-backed entity into a visitor-friendly question."""
    subject = _normalize_query(seed.subject)
    event_copy = {
        "馆娃宫与西施叙事见于地方志汇录": (
            "馆娃宫和西施的故事在地方志中有哪些记载？",
            "从灵岩山相关地方志中了解馆娃宫、西施和夫差的地方记忆，并区分传说与确证年代。",
            "地方记忆",
        ),
        "陆玩施宅为灵岩寺之说": (
            "陆玩和灵岩寺有什么历史联系？",
            "地方志以“或曰”记下这段说法，适合结合原文了解它的来历与不确定性。",
            "寺院沿革",
        ),
    }
    if seed.subject_type == "event" and subject in event_copy:
        title, summary, tag = event_copy[subject]
        prompt = f"请用通俗方式介绍“{title}”，只引用随附的本地资料，并标出文献和段落出处。"
        return title, f"{summary} {seed.summary or ''}".strip(), tag, prompt
    templates = {
        "person": (f"地方文献怎样记载{subject}与吴地的联系？", "从地方文献中看看这位人物与吴地的真实联系。", "人物故事"),
        "place": (f"{subject}为什么值得了解？", "从名称沿革、地方记载和相关事件，认识这处历史地点。", "历史地点"),
        "waterway": (f"{subject}在地方文献中有哪些记载？", "沿着地方文献中的文字，了解这条水系的名称与历史线索。", "水乡水系"),
        "bridge": (f"{subject}有哪些历史故事？", "从方志和景点资料中，了解这座桥的沿革与地方记忆。", "古桥故事"),
        "building": (f"{subject}经历过哪些变化？", "用现有文献核对它的建置、修缮和用途变化。", "建筑沿革"),
        "garden": (f"{subject}有哪些值得看的历史？", "从文献中的园林记载出发，认识它的营建与沿革。", "园林故事"),
        "event": (f"{subject}发生了什么？", "按时间、地点和人物梳理文献中可以核验的记载。", "历史事件"),
        "document": (f"{subject}记录了哪些木渎故事？", "从这份地方文献中了解木渎的地点、人物与历史记载。", "方志故事"),
    }
    title, summary, tag = templates.get(seed.subject_type, templates["place"])
    prompt = f"请用通俗方式介绍“{title}”，只引用随附的本地资料，并标出文献和段落出处。"
    return title, f"{summary} {seed.summary or ''}".strip(), tag, prompt


def _seed_chunk_ids(seed: ResearchTopicSeed) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(source.get("chunk_id")) for source in seed.sources if source.get("chunk_id")))


def _event_retrieval_query(
    title: str,
    *,
    place: str | None,
    people: tuple[str, ...],
) -> str:
    """Build a concise query that must match the event's bound source Chunk."""
    terms = [people[0]] if people else []
    if place:
        terms.append(re.sub(r"（.*?）|\(.*?\)", "", place).strip())
    return " ".join(filter(None, terms)) or title


def _topic_seed_for_query(query: str, seeds: list[ResearchTopicSeed]) -> ResearchTopicSeed | None:
    query_key = _metric_key(query)
    matches = [seed for seed in seeds if (subject_key := _metric_key(seed.subject)) and subject_key in query_key]
    if not matches:
        return None
    return max(matches, key=lambda seed: (len(_metric_key(seed.subject)), _metric_key(seed.subject)))


@lru_cache(maxsize=1)
def _load_local_knowledge_seed():  # noqa: ANN202
    """Load the checked-in evidence-bound fallback manifest once per process."""
    from deerflow.persistence.wu_culture.knowledge_seed import load_knowledge_seed

    try:
        return load_knowledge_seed(_LOCAL_KNOWLEDGE_SEED_PATH)
    except (OSError, ValueError) as exc:
        logger.warning("Local research-topic seed is unavailable: %s", type(exc).__name__)
        return None


class ResearchFeedService:
    def __init__(
        self,
        repository: ResearchFeedCandidateRepository,
        grounder: ResearchTopicGrounder,
    ) -> None:
        self._repository = repository
        self._grounder = grounder
        self._cache: dict[tuple[date, int], DailyResearchFeed] = {}
        self._verified_seeds: dict[str, tuple[ResearchTopicSeed, ...]] = {}
        self._refresh_tasks: dict[tuple[date, int], asyncio.Task[None]] = {}

    async def build_feed(self, day: date, *, limit: int = 6) -> DailyResearchFeed:
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        cache_key = (day, limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            release = await asyncio.wait_for(self._repository.get_active_release(), timeout=3)
        except Exception as exc:
            logger.warning("Research feed release lookup failed: %s", type(exc).__name__)
            return self._last_verified_feed(day, limit)
        if release is None:
            feed = DailyResearchFeed(
                generated_for=day,
                next_refresh_at=_next_refresh(day),
                items=(),
            )
            self._cache[cache_key] = feed
            return feed

        seed_notice: str | None = None
        try:
            seeds = await asyncio.wait_for(
                self._repository.list_release_topic_seeds(
                    release.id,
                    limit=_FALLBACK_SEED_LIMIT,
                ),
                timeout=2,
            )
        except Exception as exc:
            logger.warning("Research feed seed lookup failed: %s", type(exc).__name__)
            seeds = self._verified_seeds.get(release.id, ())
            if seeds:
                seed_notice = "今日内容更新暂时失败，当前展示本地精选话题"

        feed = await self._compose_feed(
            day,
            release=release,
            metrics=(),
            seeds=seeds,
            limit=limit,
            notice=seed_notice,
        )
        accepted_queries = {item.retrieval_query for item in feed.items}
        verified_seeds = tuple(seed for seed in seeds if seed.query in accepted_queries)
        if verified_seeds:
            self._verified_seeds[release.id] = verified_seeds
        self._cache[cache_key] = feed
        self._schedule_refresh(day, release=release, seeds=seeds, limit=limit)
        return feed

    async def _refresh_feed(
        self,
        day: date,
        *,
        release: ActiveReleaseSnapshot,
        seeds: tuple[ResearchTopicSeed, ...],
        limit: int,
    ) -> None:
        yesterday = day - timedelta(days=1)
        start_at = datetime.combine(yesterday, time.min, tzinfo=_SHANGHAI).astimezone(UTC)
        end_at = datetime.combine(day, time.min, tzinfo=_SHANGHAI).astimezone(UTC)
        try:
            metrics = await asyncio.wait_for(
                self._repository.list_query_metrics(
                    start_at=start_at,
                    end_at=end_at,
                    limit=_HOT_QUERY_LIMIT,
                ),
                timeout=5,
            )
            refreshed = await self._compose_feed(
                day,
                release=release,
                metrics=metrics,
                seeds=seeds,
                limit=limit,
            )
            if refreshed.items:
                self._cache[(day, limit)] = refreshed
        except Exception as exc:
            logger.warning("Research feed background refresh failed: %s", type(exc).__name__)

    def _schedule_refresh(
        self,
        day: date,
        *,
        release: ActiveReleaseSnapshot,
        seeds: tuple[ResearchTopicSeed, ...],
        limit: int,
    ) -> None:
        cache_key = (day, limit)
        existing = self._refresh_tasks.get(cache_key)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(
            self._refresh_feed(day, release=release, seeds=seeds, limit=limit),
            name=f"research-feed-refresh-{day.isoformat()}-{limit}",
        )
        self._refresh_tasks[cache_key] = task

        def discard(completed: asyncio.Task[None]) -> None:
            if self._refresh_tasks.get(cache_key) is completed:
                self._refresh_tasks.pop(cache_key, None)

        task.add_done_callback(discard)

    async def wait_for_refreshes(self) -> None:
        """Wait for currently scheduled refreshes; used by shutdown and tests."""
        tasks = tuple(self._refresh_tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def has_cached_feed(self, day: date, *, limit: int = 6) -> bool:
        return (day, limit) in self._cache

    def _last_verified_feed(self, day: date, limit: int) -> DailyResearchFeed:
        for release_id, seeds in reversed(tuple(self._verified_seeds.items())):
            release = ActiveReleaseSnapshot(id=release_id, version="本地缓存")
            return self._seed_feed(
                day,
                release=release,
                seeds=seeds,
                limit=limit,
                notice="今日内容更新暂时失败，当前展示本地精选话题",
            )
        return DailyResearchFeed(generated_for=day, next_refresh_at=_next_refresh(day), items=())

    async def _compose_feed(
        self,
        day: date,
        *,
        release: ActiveReleaseSnapshot,
        metrics: tuple[ResearchQueryMetric, ...],
        seeds: tuple[ResearchTopicSeed, ...],
        limit: int,
        notice: str | None = None,
    ) -> DailyResearchFeed:
        seeds_list = list(seeds)
        ordered_metrics = sorted(
            metrics,
            key=lambda metric: (-metric.user_count, -metric.search_count, _metric_key(metric.query)),
        )

        items: list[DailyResearchItem] = []
        accepted_topic_keys: set[str] = set()
        for metric in ordered_metrics:
            if len(items) >= limit or not _is_publishable_hot_query(metric.query):
                continue
            retrieval_query = _retrieval_query(metric.query)
            if not retrieval_query:
                continue
            topic_seed = _topic_seed_for_query(metric.query, seeds_list)
            if topic_seed is None or not topic_seed.sources:
                continue
            topic = _normalize_query(topic_seed.subject)
            topic_key = _metric_key(topic)
            if not topic_key or topic_key in accepted_topic_keys:
                continue
            topic_grounding = await self._safe_ground(
                topic_seed.query,
                release.id,
                chunk_ids=_seed_chunk_ids(topic_seed),
            )
            if not self._is_grounded(topic, topic_grounding):
                continue
            grounding = await self._safe_ground(
                retrieval_query,
                release.id,
                chunk_ids=_seed_chunk_ids(topic_seed),
            )
            if not self._is_grounded(metric.query, grounding):
                continue
            prompt = _normalize_query(metric.query)
            topic_title, topic_summary, topic_tag, _ = _public_topic_copy(topic_seed)
            items.append(
                DailyResearchItem(
                    id=_stable_id(release.id, "yesterday_hot", prompt),
                    title=topic_title,
                    summary=(f"{topic_summary} 昨日有 {metric.user_count} 位研究者发起 {metric.search_count} 次相关检索；当前知识版本命中 {grounding.evidence_count} 条可用证据。"),
                    tag=topic_tag,
                    source_basis=f"昨日真实检索 · {release.version}",
                    prompt=prompt,
                    retrieval_query=topic_seed.query,
                    origin="yesterday_hot",
                    evidence_count=grounding.evidence_count,
                    knowledge_release_id=release.id,
                    popularity_users=metric.user_count,
                    popularity_searches=metric.search_count,
                    dynasty=topic_seed.dynasty,
                    time_label=topic_seed.time_label,
                    place=topic_seed.place,
                    people=topic_seed.people,
                    entities=topic_seed.entities,
                    sources=topic_seed.sources,
                )
            )
            accepted_topic_keys.add(topic_key)

        if len(items) < limit:
            if seeds_list:
                offset = day.toordinal() % len(seeds_list)
                seeds_list = seeds_list[offset:] + seeds_list[:offset]
            for seed in seeds_list:
                if len(items) >= limit:
                    break
                topic = _normalize_query(seed.subject)
                topic_key = _metric_key(topic)
                if not topic_key or topic_key in accepted_topic_keys or not seed.sources:
                    continue
                grounding = await self._safe_ground(
                    seed.query,
                    release.id,
                    chunk_ids=_seed_chunk_ids(seed),
                )
                if not self._is_grounded(topic, grounding):
                    continue
                title, summary, tag, prompt = _public_topic_copy(seed)
                items.append(
                    DailyResearchItem(
                        id=_stable_id(release.id, "evidence_backed_fallback", prompt),
                        title=title,
                        summary=f"{summary} 当前知识版本命中 {grounding.evidence_count} 条可用证据。",
                        tag=tag,
                        source_basis=f"当前知识库证据推荐 · {release.version}",
                        prompt=prompt,
                        retrieval_query=seed.query,
                        origin="evidence_backed_fallback",
                        evidence_count=grounding.evidence_count,
                        knowledge_release_id=release.id,
                        dynasty=seed.dynasty,
                        time_label=seed.time_label,
                        place=seed.place,
                        people=seed.people,
                        entities=seed.entities,
                        sources=seed.sources,
                        degraded=True,
                        notice="部分内容暂时使用本地资料",
                    )
                )
                accepted_topic_keys.add(topic_key)

        feed = DailyResearchFeed(
            generated_for=day,
            next_refresh_at=_next_refresh(day),
            items=tuple(items),
            notice=notice or ("部分内容暂时使用本地资料" if any(item.degraded for item in items) else None),
        )
        return feed

    def _seed_feed(
        self,
        day: date,
        *,
        release: ActiveReleaseSnapshot,
        seeds: tuple[ResearchTopicSeed, ...],
        limit: int,
        notice: str,
    ) -> DailyResearchFeed:
        items: list[DailyResearchItem] = []
        rotated = list(seeds)
        if rotated:
            offset = day.toordinal() % len(rotated)
            rotated = rotated[offset:] + rotated[:offset]
        for seed in rotated:
            if len(items) >= limit or not seed.sources:
                continue
            title, summary, tag, prompt = _public_topic_copy(seed)
            grounding = GroundingResult(
                evidence_count=len(seed.sources),
                document_count=len({str(source.get("document_id")) for source in seed.sources}),
            )
            items.append(
                DailyResearchItem(
                    id=_stable_id(release.id, "evidence_backed_fallback", prompt),
                    title=title,
                    summary=f"{summary} 当前知识版本命中 {grounding.evidence_count} 条可用证据。",
                    tag=tag,
                    source_basis=f"本地已校验资料 · {release.version}",
                    prompt=prompt,
                    retrieval_query=seed.query,
                    origin="evidence_backed_fallback",
                    evidence_count=grounding.evidence_count,
                    knowledge_release_id=release.id,
                    dynasty=seed.dynasty,
                    time_label=seed.time_label,
                    place=seed.place,
                    people=seed.people,
                    entities=seed.entities,
                    sources=seed.sources,
                    degraded=True,
                    notice=notice,
                )
            )
        return DailyResearchFeed(
            generated_for=day,
            next_refresh_at=_next_refresh(day),
            items=tuple(items),
            notice=notice if items else None,
        )

    async def build_history(self, day: date, *, days: int = 7, limit: int = 6) -> DailyResearchHistory:
        if not 1 <= days <= 30:
            raise ValueError("days must be between 1 and 30")
        current = await self.build_feed(day, limit=limit)
        previous = tuple([await self.build_feed(day - timedelta(days=offset), limit=limit) for offset in range(1, days)])
        return DailyResearchHistory(current=current, previous=previous, history_days=days)

    async def _safe_ground(
        self,
        query: str,
        release_id: str,
        *,
        chunk_ids: tuple[str, ...] = (),
    ) -> GroundingResult:
        try:
            return await asyncio.wait_for(
                self._grounder.ground(
                    query,
                    release_id=release_id,
                    chunk_ids=chunk_ids,
                ),
                timeout=1.5,
            )
        except Exception as exc:
            logger.warning("Research-topic grounding failed closed: %s", type(exc).__name__)
            return GroundingResult(evidence_count=0, document_count=0)

    @staticmethod
    def _is_grounded(query: str, grounding: GroundingResult) -> bool:
        if grounding.evidence_count < _MIN_EVIDENCE_COUNT:
            return False
        if any(marker in query for marker in _COMPARISON_MARKERS) and grounding.document_count < 2:
            return False
        return True


class SqlResearchFeedCandidateRepository:
    def __init__(self, session_factory) -> None:  # noqa: ANN001
        self._session_factory = session_factory

    async def get_active_release(self) -> ActiveReleaseSnapshot | None:
        from deerflow.persistence.wu_culture import KnowledgeReleaseRow, KnowledgeReleaseStateRow

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeReleaseRow)
                    .join(
                        KnowledgeReleaseStateRow,
                        KnowledgeReleaseStateRow.active_release_id == KnowledgeReleaseRow.id,
                    )
                    .where(KnowledgeReleaseStateRow.id == "active")
                    .limit(1)
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return ActiveReleaseSnapshot(id=row.id, version=f"v{row.version_number}")

    async def list_query_metrics(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int,
    ) -> tuple[ResearchQueryMetric, ...]:
        from deerflow.persistence.run.model import RunRow

        statement = (
            select(RunRow.first_human_message, RunRow.user_id)
            .where(
                RunRow.assistant_id == "xingxi",
                RunRow.first_human_message.is_not(None),
                RunRow.created_at >= start_at,
                RunRow.created_at < end_at,
            )
            .order_by(RunRow.created_at.desc())
            .limit(5000)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()

        grouped: dict[str, dict[str, object]] = {}
        for query, user_id in rows:
            normalized = _normalize_query(query or "")
            key = _metric_key(normalized)
            if not key:
                continue
            bucket = grouped.setdefault(
                key,
                {"query": normalized, "users": set(), "search_count": 0},
            )
            users = bucket["users"]
            assert isinstance(users, set)
            users.add(user_id or "anonymous")
            bucket["search_count"] = int(bucket["search_count"]) + 1
        metrics = [
            ResearchQueryMetric(
                query=str(bucket["query"]),
                user_count=len(bucket["users"]),
                search_count=int(bucket["search_count"]),
            )
            for bucket in grouped.values()
        ]
        metrics.sort(key=lambda metric: (-metric.user_count, -metric.search_count, _metric_key(metric.query)))
        return tuple(metrics[:limit])

    async def list_release_topic_seeds(
        self,
        release_id: str,
        *,
        limit: int,
    ) -> tuple[ResearchTopicSeed, ...]:
        from deerflow.persistence.wu_culture.model import (
            EvidenceRow,
            KnowledgeReleaseItemRow,
            SourceDocumentRow,
            TextChunkRow,
            WuEntityEvidenceRow,
            WuEntityRow,
            WuEventEvidenceRow,
            WuEventParticipantRow,
            WuHistoricalEventRow,
        )

        local_seed = _load_local_knowledge_seed()

        # The checked-in manifest is deliberately small and evidence-bound.
        # Resolve only its chunk IDs against this release instead of joining
        # every graph row in the multi-gigabyte SQLite corpus.
        records = (*local_seed.entities, *local_seed.events) if local_seed is not None else ()
        expected_evidence_ids = {evidence_id for record in records for evidence_id in record.evidence_ids}
        expected_chunk_ids = {chunk_id for evidence_id in expected_evidence_ids if (chunk_id := _seed_evidence_chunk_id(evidence_id)) is not None}
        if not expected_evidence_ids and not expected_chunk_ids:
            return ()

        release_item_statement = (
            select(KnowledgeReleaseItemRow.chunk_id)
            .where(KnowledgeReleaseItemRow.release_id == release_id)
            .order_by(KnowledgeReleaseItemRow.ordinal.asc())
            # This is only a supplement to the checked-in seed. Keep the
            # window small so a cold SQLite cache cannot delay the usable
            # evidence-backed topics behind thousands of text rows.
            .limit(max(min(limit, 32), 16))
        )
        evidence_statement = (
            select(EvidenceRow, SourceDocumentRow, TextChunkRow)
            .join(SourceDocumentRow, SourceDocumentRow.id == EvidenceRow.document_id)
            .join(
                TextChunkRow,
                and_(
                    TextChunkRow.id == EvidenceRow.chunk_id,
                    TextChunkRow.document_id == EvidenceRow.document_id,
                ),
            )
            .join(
                KnowledgeReleaseItemRow,
                and_(
                    KnowledgeReleaseItemRow.release_id == release_id,
                    KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id,
                    KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id,
                ),
            )
            .where(
                EvidenceRow.review_status != "rejected",
            )
            # Chunk content can be large. Topic cards only need the stable
            # source identity, page range, and quote; loading full ORM rows
            # here made the bounded candidate query expensive on the local
            # SQLite corpus.
            .options(
                load_only(
                    EvidenceRow.id,
                    EvidenceRow.document_id,
                    EvidenceRow.chunk_id,
                    EvidenceRow.quote,
                    EvidenceRow.review_status,
                ),
                load_only(SourceDocumentRow.id, SourceDocumentRow.title),
                load_only(TextChunkRow.id, TextChunkRow.page_start, TextChunkRow.page_end),
            )
            .order_by(EvidenceRow.id.asc())
        )
        async with self._session_factory() as session:
            generic_chunk_ids = {row[0] for row in (await session.execute(release_item_statement)).all()}
            evidence_statement = evidence_statement.where(EvidenceRow.chunk_id.in_(expected_chunk_ids | generic_chunk_ids))
            evidence_rows = (await session.execute(evidence_statement)).all()
            actual_evidence_ids = tuple(evidence.id for evidence, _, _ in evidence_rows)
            entity_link_rows = (
                await session.execute(
                    select(WuEntityRow, EvidenceRow.id)
                    .join(WuEntityEvidenceRow, WuEntityEvidenceRow.entity_id == WuEntityRow.id)
                    .join(EvidenceRow, EvidenceRow.id == WuEntityEvidenceRow.evidence_id)
                    .where(
                        WuEntityRow.review_status != "rejected",
                        EvidenceRow.id.in_(actual_evidence_ids),
                    )
                )
            ).all()
            event_link_rows = (
                await session.execute(
                    select(WuHistoricalEventRow, EvidenceRow.id)
                    .join(WuEventEvidenceRow, WuEventEvidenceRow.event_id == WuHistoricalEventRow.id)
                    .join(EvidenceRow, EvidenceRow.id == WuEventEvidenceRow.evidence_id)
                    .where(
                        WuHistoricalEventRow.review_status != "rejected",
                        or_(WuHistoricalEventRow.release_id == release_id, WuHistoricalEventRow.release_id.is_(None)),
                        EvidenceRow.id.in_(actual_evidence_ids),
                    )
                )
            ).all()
            event_ids = {event.id for event, _ in event_link_rows}
            participant_rows = (
                (
                    await session.execute(
                        select(WuEventParticipantRow.event_id, WuEventParticipantRow.entity_id).where(WuEventParticipantRow.event_id.in_(event_ids)).order_by(WuEventParticipantRow.event_id, WuEventParticipantRow.entity_id)
                    )
                ).all()
                if event_ids
                else []
            )
            event_entity_ids = {entity_id for _, entity_id in participant_rows}
            event_entity_ids.update(event.place_entity_id for event, _ in event_link_rows if event.place_entity_id)
            event_entities = {entity.id: entity for entity in (await session.execute(select(WuEntityRow).where(WuEntityRow.id.in_(event_entity_ids)))).scalars()} if event_entity_ids else {}

        rows_by_evidence = {evidence.id: (evidence, document, chunk) for evidence, document, chunk in evidence_rows}
        rows_by_chunk: dict[str, tuple[EvidenceRow, SourceDocumentRow, TextChunkRow]] = {}
        for row in evidence_rows:
            rows_by_chunk.setdefault(row[0].chunk_id, row)

        def source_rows_for(record) -> tuple[tuple[EvidenceRow, SourceDocumentRow, TextChunkRow], ...]:  # noqa: ANN001
            rows = []
            seen: set[str] = set()
            for evidence_id in record.evidence_ids:
                row = rows_by_evidence.get(evidence_id)
                if row is None:
                    chunk_id = _seed_evidence_chunk_id(evidence_id)
                    row = rows_by_chunk.get(chunk_id) if chunk_id else None
                if row is not None and row[0].id not in seen:
                    rows.append(row)
                    seen.add(row[0].id)
            return tuple(rows)

        def source_payloads(source_rows) -> tuple[dict[str, str | int | None], ...]:  # noqa: ANN001
            return tuple(
                {
                    "evidence_id": evidence.id,
                    "document_id": document.id,
                    "document_title": document.title,
                    "chunk_id": chunk.id,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "quote": evidence.quote,
                }
                for evidence, document, chunk in source_rows[:8]
            )

        entity_by_id = {entity.id: entity for entity in local_seed.entities} if local_seed is not None else {}
        buckets: dict[str, list[ResearchTopicSeed]] = {}
        known: set[str] = set()

        for entity in local_seed.entities if local_seed is not None else ():
            title = _normalize_query(entity.canonical_name)
            source_rows = source_rows_for(entity)
            key = _metric_key(title)
            if not title or not key or key in known or not source_rows:
                continue
            entity_type = entity.entity_type.value
            entity_ref = {"id": entity.id, "name": title, "entity_type": entity_type}
            buckets.setdefault(entity_type, []).append(
                ResearchTopicSeed(
                    query=title,
                    subject=title,
                    subject_type=entity_type,
                    summary=entity.summary,
                    dynasty=entity.dynasty,
                    time_label=entity.dynasty or "年代待考",
                    place=title if entity_type in {"place", "waterway", "bridge", "building", "garden"} else None,
                    people=(title,) if entity_type == "person" else (),
                    entities=(entity_ref,),
                    sources=source_payloads(source_rows),
                )
            )
            known.add(key)

        for event in local_seed.events if local_seed is not None else ():
            title = _normalize_query(event.title)
            source_rows = source_rows_for(event)
            key = _metric_key(title)
            if not title or not key or key in known or not source_rows:
                continue
            place = entity_by_id.get(event.place_entity_id) if event.place_entity_id else None
            participants = [entity_by_id[entity_id] for entity_id in event.participant_entity_ids if entity_id in entity_by_id]
            entity_refs = (
                {"id": event.id, "name": title, "entity_type": "event"},
                *({"id": entity.id, "name": entity.canonical_name, "entity_type": entity.entity_type.value} for entity in ([place] if place else []) + participants),
            )
            time_label = "年代待考"
            if event.start_time:
                time_label = f"{event.start_time}{'年' if event.start_time.isdigit() else ''}"
                if event.time_certainty.value != "exact":
                    time_label = f"约{time_label}"
            dynasty = next((entity.dynasty for entity in participants if entity.dynasty), None) or (place.dynasty if place else None)
            people = tuple(entity.canonical_name for entity in participants if entity.entity_type.value == "person")
            place_name = place.canonical_name if place else None
            buckets.setdefault("event", []).append(
                ResearchTopicSeed(
                    query=_event_retrieval_query(
                        title,
                        place=place_name,
                        people=people,
                    ),
                    subject=title,
                    subject_type="event",
                    summary=event.summary,
                    dynasty=dynasty,
                    time_label=time_label,
                    place=place_name,
                    people=people,
                    entities=entity_refs,
                    sources=source_payloads(source_rows),
                )
            )
            known.add(key)

        # Include newly ingested, evidence-bound records as a small supplement
        # to the reviewed local manifest. The release-item cap keeps this path
        # bounded and lets the checked-in manifest cover records outside that
        # first window.
        grouped_entities: dict[str, tuple[WuEntityRow, list[tuple[EvidenceRow, SourceDocumentRow, TextChunkRow]]]] = {}
        for entity, evidence_id in entity_link_rows:
            row = rows_by_evidence.get(evidence_id)
            if row is None:
                continue
            grouped_entities.setdefault(entity.id, (entity, []))[1].append(row)
        for entity, source_rows in grouped_entities.values():
            title = _normalize_query(entity.canonical_name)
            key = _metric_key(title)
            if not title or not key or key in known:
                continue
            entity_type = entity.entity_type
            buckets.setdefault(entity_type, []).append(
                ResearchTopicSeed(
                    query=title,
                    subject=title,
                    subject_type=entity_type,
                    summary=entity.summary,
                    dynasty=entity.dynasty,
                    time_label=entity.dynasty or "年代待考",
                    place=title if entity_type in {"place", "waterway", "bridge", "building", "garden"} else None,
                    people=(title,) if entity_type == "person" else (),
                    entities=(({"id": entity.id, "name": title, "entity_type": entity_type}),),
                    sources=source_payloads(source_rows),
                )
            )
            known.add(key)

        entity_by_id.update(event_entities)
        grouped_events: dict[str, tuple[WuHistoricalEventRow, list[tuple[EvidenceRow, SourceDocumentRow, TextChunkRow]]]] = {}
        for event, evidence_id in event_link_rows:
            row = rows_by_evidence.get(evidence_id)
            if row is None:
                continue
            grouped_events.setdefault(event.id, (event, []))[1].append(row)
        for event, source_rows in grouped_events.values():
            title = _normalize_query(event.title)
            key = _metric_key(title)
            if not title or not key or key in known:
                continue
            place = entity_by_id.get(event.place_entity_id) if event.place_entity_id else None
            participant_ids = [entity_id for event_id, entity_id in participant_rows if event_id == event.id]
            participants = [entity_by_id[entity_id] for entity_id in participant_ids if entity_id in entity_by_id]
            entity_refs = (
                {"id": event.id, "name": title, "entity_type": "event"},
                *(
                    {
                        "id": entity.id,
                        "name": entity.canonical_name,
                        "entity_type": entity.entity_type,
                    }
                    for entity in ([place] if place else []) + participants
                ),
            )
            time_label = "年代待考"
            if event.start_time:
                time_label = f"{event.start_time}{'年' if event.start_time.isdigit() else ''}"
                if event.time_certainty != "exact":
                    time_label = f"约{time_label}"
            dynasty = next((entity.dynasty for entity in participants if entity.dynasty), None) or (place.dynasty if place else None)
            people = tuple(entity.canonical_name for entity in participants if entity.entity_type == "person")
            place_name = place.canonical_name if place else None
            buckets.setdefault("event", []).append(
                ResearchTopicSeed(
                    query=_event_retrieval_query(
                        title,
                        place=place_name,
                        people=people,
                    ),
                    subject=title,
                    subject_type="event",
                    summary=event.summary,
                    dynasty=dynasty,
                    time_label=time_label,
                    place=place_name,
                    people=people,
                    entities=entity_refs,
                    sources=source_payloads(source_rows),
                )
            )
            known.add(key)

        # Rotate across entity kinds so the fallback has visitor-facing
        # variety instead of returning only the most frequently cited people.
        type_order = (
            "place",
            "event",
            "waterway",
            "bridge",
            "building",
            "garden",
            "person",
            "relic",
            "work",
        )
        ordered_types = [*type_order, *(key for key in buckets if key not in type_order)]
        seeds: list[ResearchTopicSeed] = []
        while len(seeds) < limit:
            added = False
            for subject_type in ordered_types:
                bucket = buckets.get(subject_type)
                if not bucket:
                    continue
                seeds.append(bucket.pop(0))
                added = True
                if len(seeds) >= limit:
                    break
            if not added:
                break
        return tuple(seeds)


class SqlResearchTopicGrounder:
    def __init__(self, session_factory) -> None:  # noqa: ANN001
        self._session_factory = session_factory
        self._cache: dict[tuple[str, str], GroundingResult] = {}

    async def ground(
        self,
        query: str,
        *,
        release_id: str,
        chunk_ids: tuple[str, ...] = (),
    ) -> GroundingResult:
        normalized_chunk_ids = tuple(dict.fromkeys(chunk_ids))
        key = (release_id, _metric_key(query), normalized_chunk_ids)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        from deerflow.persistence.wu_culture import FullTextDocumentRow, SourceDocumentRow
        from deerflow.persistence.wu_culture.repository import (
            SqlSourceDocumentRepository,
            _script_variants,
        )

        parsed = parse_fulltext_query(query)
        groups = tuple(_script_variants(term) for term in parsed.all_terms)
        if not groups:
            return GroundingResult(evidence_count=0, document_count=0)
        statement = (
            select(FullTextDocumentRow, SourceDocumentRow)
            .join(SourceDocumentRow, SourceDocumentRow.id == FullTextDocumentRow.document_id)
            .where(FullTextDocumentRow.release_id == release_id)
            .order_by(FullTextDocumentRow.id.asc())
            .limit(100)
        )
        if normalized_chunk_ids:
            statement = statement.where(FullTextDocumentRow.chunk_id.in_(normalized_chunk_ids))
        for variants in groups:
            statement = statement.where(or_(*(FullTextDocumentRow.search_text.contains(value, autoescape=True) for value in variants)))
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()

        authorized_rows = [
            row
            for row in rows
            if evaluate_source_access(
                SqlSourceDocumentRepository._row_to_document(row[1]),
                use=AuthorizedUse.INTERNAL_PROCESSING,
            ).allowed
        ][:20]
        result = GroundingResult(
            evidence_count=len(authorized_rows),
            document_count=len({fulltext.document_id for fulltext, _ in authorized_rows}),
        )
        self._cache[key] = result
        return result


@lru_cache(maxsize=1)
def get_research_feed_service() -> ResearchFeedService:
    session_factory = get_session_factory()
    if session_factory is None:
        return ResearchFeedService(_EmptyCandidateRepository(), _EmptyGrounder())
    return ResearchFeedService(
        SqlResearchFeedCandidateRepository(session_factory),
        SqlResearchTopicGrounder(session_factory),
    )


class _EmptyCandidateRepository:
    async def get_active_release(self) -> ActiveReleaseSnapshot | None:
        return None

    async def list_query_metrics(self, *, start_at: datetime, end_at: datetime, limit: int) -> tuple[ResearchQueryMetric, ...]:
        return ()

    async def list_release_topic_seeds(self, release_id: str, *, limit: int) -> tuple[ResearchTopicSeed, ...]:
        return ()


class _EmptyGrounder:
    async def ground(
        self,
        query: str,
        *,
        release_id: str,
        chunk_ids: tuple[str, ...] = (),
    ) -> GroundingResult:
        return GroundingResult(evidence_count=0, document_count=0)


@router.get("/daily", response_model=DailyResearchFeed)
async def get_daily_research_feed(
    response: Response,
    limit: int = Query(default=6, ge=4, le=6),
    service: ResearchFeedService = Depends(get_research_feed_service),
) -> DailyResearchFeed:
    day = _now_shanghai().date()
    delivery = "cache" if service.has_cached_feed(day, limit=limit) else "seed"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Research-Feed-Delivery"] = delivery
    return await service.build_feed(day, limit=limit)


@router.get("/history", response_model=DailyResearchHistory)
async def get_daily_research_history(
    response: Response,
    days: int = Query(default=7, ge=1, le=30),
    service: ResearchFeedService = Depends(get_research_feed_service),
) -> DailyResearchHistory:
    response.headers["Cache-Control"] = "no-store"
    return await service.build_history(_now_shanghai().date(), days=days)
