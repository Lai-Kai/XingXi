"""Evidence-gated daily research topics for the Xingxi workspace."""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, distinct, func, or_, select
from wu_culture import AuthorizedUse, evaluate_source_access
from wu_culture.fulltext import parse_fulltext_query

from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/research-feed", tags=["research-feed"])

logger = logging.getLogger(__name__)
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_MIN_EVIDENCE_COUNT = 2
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


class DailyResearchItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    summary: str
    tag: str
    source_basis: str
    prompt: str
    origin: Literal["yesterday_hot", "evidence_backed_fallback"]
    evidence_count: int = Field(ge=_MIN_EVIDENCE_COUNT)
    knowledge_release_id: str
    popularity_users: int | None = Field(default=None, ge=1)
    popularity_searches: int | None = Field(default=None, ge=1)


class DailyResearchFeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["daily_grounded"] = "daily_grounded"
    generated_for: date
    next_refresh_at: datetime
    items: tuple[DailyResearchItem, ...]


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
    async def ground(self, query: str, *, release_id: str) -> GroundingResult: ...


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
            topic,
            f"从当前已发布方志证据中梳理{topic}的生平、活动地点和相关事件。",
            "人物考证",
            f"梳理{topic}的生平活动与地方记载，逐条列出可核验出处。",
        ),
        "place": (
            topic,
            f"从当前已发布文献中核对{topic}的名称、沿革与相关历史事件。",
            "历史地理",
            f"研究{topic}的历史沿革与方志记载，区分明确记载与后世推断。",
        ),
        "waterway": (
            topic,
            f"依据当前已发布文献整理{topic}的名称、河道关系与历代变化。",
            "水系考证",
            f"梳理{topic}水系的历史沿革，并列出可核验的方志证据。",
        ),
        "bridge": (
            topic,
            f"核对当前已发布文献中{topic}的名称、位置和历次修建记载。",
            "古迹考证",
            f"考证{topic}的名称、位置与重修记录，并标明证据出处。",
        ),
        "building": (
            topic,
            f"从当前已发布方志材料中梳理{topic}的建置、修缮和功能变化。",
            "建筑史",
            f"考证{topic}的建置与沿革，并逐条列出方志依据。",
        ),
        "garden": (
            topic,
            f"从当前已发布材料中区分{topic}的始建、扩建和修缮年代。",
            "园林史",
            f"核验{topic}的营建与修缮记录，并比较可引用证据。",
        ),
        "event": (
            topic,
            f"依据当前已发布史料核对{topic}的时间、地点、人物和后续影响。",
            "历史事件",
            f"考证{topic}的时间、地点与影响，并列出可核验出处。",
        ),
        "document": (
            topic,
            f"从当前已发布索引中梳理{topic}的版本、卷目和可检索内容。",
            "方志版本",
            f"核对{topic}的版本、卷目与原文出处，并引用当前知识库中的原文位置。",
        ),
    }
    return templates.get(seed.subject_type, templates["place"])


def _topic_seed_for_query(query: str, seeds: list[ResearchTopicSeed]) -> ResearchTopicSeed | None:
    query_key = _metric_key(query)
    matches = [seed for seed in seeds if (subject_key := _metric_key(seed.subject)) and subject_key in query_key]
    if not matches:
        return None
    return max(matches, key=lambda seed: (len(_metric_key(seed.subject)), _metric_key(seed.subject)))


class ResearchFeedService:
    def __init__(
        self,
        repository: ResearchFeedCandidateRepository,
        grounder: ResearchTopicGrounder,
    ) -> None:
        self._repository = repository
        self._grounder = grounder

    async def build_feed(self, day: date, *, limit: int = 2) -> DailyResearchFeed:
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        release = await self._repository.get_active_release()
        if release is None:
            return DailyResearchFeed(
                generated_for=day,
                next_refresh_at=_next_refresh(day),
                items=(),
            )

        yesterday = day - timedelta(days=1)
        start_at = datetime.combine(yesterday, time.min, tzinfo=_SHANGHAI).astimezone(UTC)
        end_at = datetime.combine(day, time.min, tzinfo=_SHANGHAI).astimezone(UTC)
        metrics = await self._repository.list_query_metrics(
            start_at=start_at,
            end_at=end_at,
            limit=_HOT_QUERY_LIMIT,
        )
        seeds = list(
            await self._repository.list_release_topic_seeds(
                release.id,
                limit=_FALLBACK_SEED_LIMIT,
            )
        )
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
            topic_seed = _topic_seed_for_query(metric.query, seeds)
            if topic_seed is None:
                continue
            topic = _normalize_query(topic_seed.subject)
            topic_key = _metric_key(topic)
            if not topic_key or topic_key in accepted_topic_keys:
                continue
            topic_grounding = await self._safe_ground(topic, release.id)
            if not self._is_grounded(topic, topic_grounding):
                continue
            grounding = await self._safe_ground(retrieval_query, release.id)
            if not self._is_grounded(metric.query, grounding):
                continue
            prompt = _normalize_query(metric.query)
            items.append(
                DailyResearchItem(
                    id=_stable_id(release.id, "yesterday_hot", prompt),
                    title=topic,
                    summary=(f"昨日有 {metric.user_count} 位研究者发起 {metric.search_count} 次相关检索；当前知识版本命中 {grounding.evidence_count} 条可用证据。"),
                    tag="昨日热门",
                    source_basis=f"昨日真实检索 · {release.version}",
                    prompt=prompt,
                    origin="yesterday_hot",
                    evidence_count=grounding.evidence_count,
                    knowledge_release_id=release.id,
                    popularity_users=metric.user_count,
                    popularity_searches=metric.search_count,
                )
            )
            accepted_topic_keys.add(topic_key)

        if len(items) < limit:
            if seeds:
                offset = day.toordinal() % len(seeds)
                seeds = seeds[offset:] + seeds[:offset]
            for seed in seeds:
                if len(items) >= limit:
                    break
                topic = _normalize_query(seed.subject)
                topic_key = _metric_key(topic)
                if not topic_key or topic_key in accepted_topic_keys:
                    continue
                grounding = await self._safe_ground(topic, release.id)
                if not self._is_grounded(topic, grounding):
                    continue
                title, summary, tag, prompt = _fallback_copy(seed)
                items.append(
                    DailyResearchItem(
                        id=_stable_id(release.id, "evidence_backed_fallback", prompt),
                        title=title,
                        summary=f"{summary} 当前知识版本命中 {grounding.evidence_count} 条可用证据。",
                        tag=tag,
                        source_basis=f"当前知识库证据推荐 · {release.version}",
                        prompt=prompt,
                        origin="evidence_backed_fallback",
                        evidence_count=grounding.evidence_count,
                        knowledge_release_id=release.id,
                    )
                )
                accepted_topic_keys.add(topic_key)

        return DailyResearchFeed(
            generated_for=day,
            next_refresh_at=_next_refresh(day),
            items=tuple(items),
        )

    async def build_history(self, day: date, *, days: int = 7, limit: int = 2) -> DailyResearchHistory:
        if not 1 <= days <= 30:
            raise ValueError("days must be between 1 and 30")
        current = await self.build_feed(day, limit=limit)
        previous = tuple([await self.build_feed(day - timedelta(days=offset), limit=limit) for offset in range(1, days)])
        return DailyResearchHistory(current=current, previous=previous, history_days=days)

    async def _safe_ground(self, query: str, release_id: str) -> GroundingResult:
        try:
            return await self._grounder.ground(query, release_id=release_id)
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
        from deerflow.persistence.wu_culture import FullTextDocumentRow
        from deerflow.persistence.wu_culture.model import (
            EvidenceRow,
            KnowledgeReleaseItemRow,
            WuEventEvidenceRow,
            WuEntityEvidenceRow,
            WuEntityRow,
            WuHistoricalEventRow,
        )

        entity_statement = (
            select(
                WuEntityRow.canonical_name,
                WuEntityRow.entity_type,
                func.count(distinct(EvidenceRow.id)).label("evidence_count"),
            )
            .join(WuEntityEvidenceRow, WuEntityEvidenceRow.entity_id == WuEntityRow.id)
            .join(EvidenceRow, EvidenceRow.id == WuEntityEvidenceRow.evidence_id)
            .join(
                KnowledgeReleaseItemRow,
                and_(
                    KnowledgeReleaseItemRow.release_id == release_id,
                    KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id,
                    KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id,
                ),
            )
            .group_by(WuEntityRow.id, WuEntityRow.canonical_name, WuEntityRow.entity_type)
            .order_by(func.count(distinct(EvidenceRow.id)).desc(), WuEntityRow.canonical_name.asc())
        )
        document_statement = (
            select(FullTextDocumentRow.document_title, func.count(FullTextDocumentRow.id).label("chunk_count"))
            .where(FullTextDocumentRow.release_id == release_id)
            .group_by(FullTextDocumentRow.document_title)
            .order_by(func.count(FullTextDocumentRow.id).desc(), FullTextDocumentRow.document_title.asc())
            .limit(limit)
        )
        event_statement = (
            select(
                WuHistoricalEventRow.title,
                func.count(distinct(EvidenceRow.id)).label("evidence_count"),
            )
            .join(
                WuEventEvidenceRow,
                WuEventEvidenceRow.event_id == WuHistoricalEventRow.id,
            )
            .join(EvidenceRow, EvidenceRow.id == WuEventEvidenceRow.evidence_id)
            .join(
                KnowledgeReleaseItemRow,
                and_(
                    KnowledgeReleaseItemRow.release_id == release_id,
                    KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id,
                    KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id,
                ),
            )
            .where(WuHistoricalEventRow.review_status != "rejected")
            .group_by(WuHistoricalEventRow.id, WuHistoricalEventRow.title)
            .order_by(
                func.count(distinct(EvidenceRow.id)).desc(),
                WuHistoricalEventRow.title.asc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            entity_rows = (await session.execute(entity_statement)).all()
            document_rows = (await session.execute(document_statement)).all()
            event_rows = (await session.execute(event_statement)).all()

        buckets: dict[str, list[ResearchTopicSeed]] = {}
        known: set[str] = set()

        def add_seed(name: str | None, subject_type: str) -> None:
            normalized = _normalize_query(name or "")
            key = _metric_key(normalized)
            if not normalized or not key or key in known:
                return
            buckets.setdefault(subject_type, []).append(
                ResearchTopicSeed(
                    query=normalized,
                    subject=normalized,
                    subject_type=subject_type,
                )
            )
            known.add(key)

        for name, entity_type, _ in entity_rows:
            add_seed(name, entity_type)
        for title, _ in document_rows:
            add_seed(title, "document")
        for title, _ in event_rows:
            add_seed(title, "event")

        # Evidence frequency alone over-selects people because the same person
        # is mentioned in many catalogue passages. Round-robin the verified
        # entity buckets so places, buildings, bridges, waterways, events and
        # documents can all become daily topics.
        type_order = (
            "person",
            "place",
            "building",
            "bridge",
            "waterway",
            "garden",
            "relic",
            "event",
            "document",
            "work",
            "organization",
            "family",
        )
        ordered_types = [*type_order, *(key for key in buckets if key not in type_order)]
        seeds: list[ResearchTopicSeed] = []
        while len(seeds) < limit and any(buckets.get(subject_type) for subject_type in ordered_types):
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

    async def ground(self, query: str, *, release_id: str) -> GroundingResult:
        key = (release_id, _metric_key(query))
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
    async def ground(self, query: str, *, release_id: str) -> GroundingResult:
        return GroundingResult(evidence_count=0, document_count=0)


@router.get("/daily", response_model=DailyResearchFeed)
async def get_daily_research_feed(
    response: Response,
    service: ResearchFeedService = Depends(get_research_feed_service),
) -> DailyResearchFeed:
    response.headers["Cache-Control"] = "no-store"
    return await service.build_feed(_now_shanghai().date())


@router.get("/history", response_model=DailyResearchHistory)
async def get_daily_research_history(
    response: Response,
    days: int = Query(default=7, ge=1, le=30),
    service: ResearchFeedService = Depends(get_research_feed_service),
) -> DailyResearchHistory:
    response.headers["Cache-Control"] = "no-store"
    return await service.build_history(_now_shanghai().date(), days=days)
