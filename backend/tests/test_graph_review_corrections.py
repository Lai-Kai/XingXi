"""Real SQL and HTTP regressions for repeatable relation/event review."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture.events import EventCreate
from wu_culture.models import ReviewStatus
from wu_culture.relations import RelationCreate

from app.gateway.routers import knowledge_graph
from deerflow.persistence.base import Base
from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade
from deerflow.persistence.wu_culture.graph_repository import SqlKnowledgeGraphRepository
from deerflow.persistence.wu_culture.model import (
    WU_CULTURE_TABLES,
    EvidenceRow,
    SourceDocumentRow,
    TextChunkRow,
    WuEntityEvidenceRow,
    WuEntityRow,
    WuEventEvidenceRow,
    WuEventParticipantRow,
    WuHistoricalEventRow,
    WuRelationEvidenceRow,
    WuRelationRow,
)
from deerflow.persistence.wu_culture.temporal_repository import SqlEventRepository


@pytest_asyncio.fixture
async def review_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'review.db'}")
    sa.event.listen(engine.sync_engine, "connect", lambda db, _record: db.execute("PRAGMA foreign_keys=ON"))
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=WU_CULTURE_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory.begin() as session:
        session.add(SourceDocumentRow(id="doc", title="测试方志", source_type="gazetteer", source_level="A", copyright_status="public_domain"))
        await session.flush()
        session.add(TextChunkRow(id="chunk", document_id="doc", original_text="测试史料", normalized_text="测试史料", page_start=1, page_end=1, review_status="reviewed"))
        await session.flush()
        session.add(EvidenceRow(id="ev", document_id="doc", chunk_id="chunk", quote="测试史料", source_level="A", review_status="reviewed"))
        session.add_all(WuEntityRow(id=key, canonical_name=key, entity_type="person", review_status="reviewed", created_at=now, updated_at=now) for key in ("a", "b"))
        await session.flush()
        session.add_all(WuEntityEvidenceRow(entity_id=key, evidence_id="ev") for key in ("a", "b"))
        session.add(WuRelationRow(id="relation", subject_id="a", object_id="b", relation_type="related_to", confidence=0.8, review_status="pending", created_at=now, updated_at=now))
        session.add(WuHistoricalEventRow(id="event", title="测试事件", event_type="visit", time_certainty="unknown", review_status="pending", created_at=now, updated_at=now))
        await session.flush()
        session.add(WuRelationEvidenceRow(relation_id="relation", evidence_id="ev"))
        session.add(WuEventEvidenceRow(event_id="event", evidence_id="ev"))
        session.add(WuEventParticipantRow(event_id="event", entity_id="a"))
    graph = SqlKnowledgeGraphRepository(factory)
    events = SqlEventRepository(factory)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user = SimpleNamespace(id="reviewer-1", system_role=request.headers.get("x-test-role", "admin"))
        return await call_next(request)

    async def current_user(request):
        return request.state.user

    async def release_id(requested):
        return requested

    monkeypatch.setattr(knowledge_graph, "get_current_user_from_request", current_user)
    monkeypatch.setattr(knowledge_graph, "_resolve_active_release_id", release_id)
    app.include_router(knowledge_graph.router)
    app.dependency_overrides[knowledge_graph.get_graph_repository] = lambda: graph
    app.dependency_overrides[knowledge_graph.get_event_repository] = lambda: events
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, graph, events, factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["relation", "event"])
async def test_continuous_review_appends_history_and_rejected_is_admin_only(review_db, kind):
    client, graph, events, _factory = review_db
    path = f"/api/knowledge-graph/{kind}s"
    previous = "pending"
    snapshots = []
    for index, status in enumerate(("rejected", "reviewed", "pending", "disputed", "reviewed", "disputed", "rejected", "pending", "reviewed", "rejected", "disputed", "pending"), start=1):
        response = await client.patch(f"{path}/{kind}/review", json={"review_status": status, "expected_status": previous, "review_note": f"复核依据 {index}"})
        assert response.status_code == 200, response.text
        assert response.json()["review_status"] == status
        assert [row["id"] for row in (await client.get(path, params={"include_rejected": "true"})).json()] == [kind]
        ordinary = (await client.get(path)).json()
        assert [row["id"] for row in ordinary] == ([] if status == "rejected" else [kind])
        if kind == "relation":
            for filters in ({}, {"entity_id": "a"}):
                assert [r.id for r in await graph.list_relations(**filters)] == ([] if status == "rejected" else [kind])
                assert [r.id for r in await graph.list_relations(**filters, include_rejected=True)] == [kind]
            assert [r.id for r in await graph.relations_for_entities(("a",))] == ([] if status == "rejected" else [kind])
            query = (await client.get("/api/knowledge-graph/query", params={"entity": "a"})).json()
            assert [r["id"] for r in query["edges"]] == ([] if status == "rejected" else [kind])
        else:
            stored = await events.get(kind)
            assert (stored is None) == (status == "rejected")
            assert [r.id for r in await events.list(include_rejected=True, participant_entity_id="a")] == [kind]
        history = await client.get(f"{path}/{kind}/review-history")
        assert history.status_code == 200, history.text
        rows = history.json()
        assert rows[:-1] == snapshots
        assert len(rows) == index
        assert rows[-1].items() >= {"object_type": kind, "object_id": kind, "previous_status": previous, "new_status": status, "reviewer_id": "reviewer-1", "review_note": f"复核依据 {index}"}.items()
        assert datetime.fromisoformat(rows[-1]["created_at"]).tzinfo is not None
        snapshots = rows
        previous = status


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["relation", "event"])
async def test_rejected_reads_review_and_history_require_admin(review_db, kind):
    client, *_ = review_db
    path = f"/api/knowledge-graph/{kind}s"
    assert (await client.patch(f"{path}/{kind}/review", json={"review_status": "rejected", "review_note": "测试驳回"})).status_code == 200
    headers = {"x-test-role": "user"}
    assert (await client.get(path, headers=headers)).json() == []
    for params in ({"include_rejected": "true"}, {"include_rejected": "1"}):
        assert (await client.get(path, params=params, headers=headers)).status_code == 403
    assert (await client.get(f"{path}/{kind}/review-history", headers=headers)).status_code == 403
    assert (await client.patch(f"{path}/{kind}/review", headers=headers, json={"review_status": "reviewed", "review_note": "越权"})).status_code == 403


@pytest.mark.asyncio
async def test_admin_rejected_relation_queue_recovers_unbacked_legacy_rows(review_db):
    client, _graph, _events, factory = review_db
    async with factory.begin() as session:
        session.add(
            WuRelationRow(
                id="legacy-rejected",
                subject_id="a",
                object_id="b",
                relation_type="visited",
                confidence=0.1,
                is_inferred=False,
                review_status="rejected",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    ordinary = (await client.get("/api/knowledge-graph/relations")).json()
    assert {row["id"] for row in ordinary} == {"relation"}
    privileged = (await client.get("/api/knowledge-graph/relations", params={"include_rejected": "true"})).json()
    assert {row["id"] for row in privileged} == {"relation", "legacy-rejected"}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["relation", "event"])
async def test_notes_evidence_and_stale_decisions_preserve_state_and_history(review_db, kind):
    client, graph, events, _factory = review_db
    path = f"/api/knowledge-graph/{kind}s/{kind}"
    for status in ("rejected", "disputed"):
        for note in (None, "  "):
            response = await client.patch(f"{path}/review", json={"review_status": status, "review_note": note})
            assert response.status_code == 400, response.text
    assert (await client.get(f"{path}/review-history")).json() == []
    assert (await client.patch(f"{path}/review", json={"review_status": "reviewed"})).status_code == 200
    history = (await client.get(f"{path}/review-history")).json()
    for status in ("pending", "rejected", "disputed", "reviewed"):
        assert (await client.patch(f"{path}/review", json={"review_status": status})).status_code == 400
    stale = await client.patch(f"{path}/review", json={"review_status": "rejected", "expected_status": "pending", "review_note": "过期界面"})
    assert stale.status_code == 409
    assert (await client.get(f"{path}/review-history")).json() == history
    assert (await client.get(f"/api/knowledge-graph/{kind}s")).json()[0]["review_status"] == "reviewed"
    if kind == "relation":
        await graph.create_relation(RelationCreate(id="unbacked", subject_id="a", object_id="b", relation_type="visited", is_inferred=True))
    else:
        await events.create(EventCreate(id="unbacked", title="无证据事件", event_type="visit", is_inferred=True))
    response = await client.patch(f"/api/knowledge-graph/{kind}s/unbacked/review", json={"review_status": "reviewed"})
    assert response.status_code == 400
    assert "evidence" in response.json()["detail"].lower()
    assert (await client.get(f"/api/knowledge-graph/{kind}s/unbacked/review-history")).json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["relation", "event"])
async def test_failed_history_insert_rolls_back_status_and_history_cannot_be_edited(review_db, kind):
    from deerflow.persistence.wu_culture.model import GraphReviewRecordRow

    client, graph, events, factory = review_db
    review = graph.review_relation if kind == "relation" else events.review

    def fail_insert(*_args):
        raise RuntimeError("audit storage unavailable")

    sa.event.listen(GraphReviewRecordRow, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="audit storage"):
            await review(kind, ReviewStatus.REJECTED, reviewer_id="reviewer-1", review_note="记录失败")
    finally:
        sa.event.remove(GraphReviewRecordRow, "before_insert", fail_insert)
    path = f"/api/knowledge-graph/{kind}s"
    assert (await client.get(path)).json()[0]["review_status"] == "pending"
    assert (await client.get(f"{path}/{kind}/review-history")).json() == []
    await review(kind, ReviewStatus.REVIEWED, reviewer_id="reviewer-1")
    for remove in (False, True):
        async with factory() as session:
            row = (await session.execute(sa.select(GraphReviewRecordRow))).scalar_one()
            if remove:
                await session.delete(row)
            else:
                row.review_note = "改写旧记录"
            with pytest.raises(ValueError, match="immutable"):
                await session.commit()
    assert len((await client.get(f"{path}/{kind}/review-history")).json()) == 1


@pytest.mark.asyncio
async def test_review_does_not_rewrite_published_release_or_active_pointer(review_db):
    from deerflow.persistence.wu_culture.model import KnowledgeReleaseRow, KnowledgeReleaseStateRow

    _client, graph, events, factory = review_db
    async with factory.begin() as session:
        session.add(KnowledgeReleaseRow(id="published", version_number=1, release_notes="历史版本", status="active", manifest_sha256="a" * 64, created_by="publisher", created_at=datetime.now(UTC)))
        await session.flush()
        session.add(KnowledgeReleaseStateRow(id="active", active_release_id="published", state_version=3, updated_by="publisher"))
        await session.execute(sa.update(WuRelationRow).values(release_id="published"))
        await session.execute(sa.update(WuHistoricalEventRow).values(release_id="published"))
    async with factory() as session:
        before_release = dict((await session.execute(sa.select(KnowledgeReleaseRow.__table__))).mappings().one())
        before_state = dict((await session.execute(sa.select(KnowledgeReleaseStateRow.__table__))).mappings().one())
    await graph.review_relation("relation", ReviewStatus.REJECTED, reviewer_id="reviewer-1", review_note="工作记录纠错")
    await events.review("event", ReviewStatus.DISPUTED, reviewer_id="reviewer-1", review_note="工作记录存疑")
    async with factory() as session:
        assert dict((await session.execute(sa.select(KnowledgeReleaseRow.__table__))).mappings().one()) == before_release
        assert dict((await session.execute(sa.select(KnowledgeReleaseStateRow.__table__))).mappings().one()) == before_state
        assert (await session.get(WuRelationRow, "relation")).release_id == "published"
        assert (await session.get(WuHistoricalEventRow, "event")).release_id == "published"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["relation", "event"])
async def test_concurrent_review_allows_only_one_change_from_the_same_status(review_db, kind):
    from wu_culture.review import ReviewConflictError

    client, graph, events, _factory = review_db
    review = graph.review_relation if kind == "relation" else events.review
    results = await asyncio.gather(
        review(kind, ReviewStatus.REVIEWED, reviewer_id="reviewer-a", expected_status=ReviewStatus.PENDING),
        review(kind, ReviewStatus.REJECTED, reviewer_id="reviewer-b", review_note="依据存疑", expected_status=ReviewStatus.PENDING),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ReviewConflictError) for result in results) == 1, results
    history = (await client.get(f"/api/knowledge-graph/{kind}s/{kind}/review-history")).json()
    assert len(history) == 1
    assert history[0]["previous_status"] == "pending"


@pytest.mark.asyncio
async def test_review_migration_adds_history_without_rewriting_existing_records(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrade.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0042_prune_unbacked_graph")
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO wu_historical_events (id,title,event_type,time_certainty,is_inferred,review_status,created_at,updated_at) VALUES ('old','旧记录','visit','unknown',1,'rejected',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
            )
        await asyncio.to_thread(_upgrade, config, "0043_graph_review_history")
        async with engine.connect() as conn:
            assert (await conn.execute(sa.text("SELECT review_status FROM wu_historical_events WHERE id='old'"))).scalar_one() == "rejected"
            assert (await conn.execute(sa.text("SELECT count(*) FROM wu_graph_review_records"))).scalar_one() == 0
        from deerflow.persistence.operations import OperationsRepository

        factory = async_sessionmaker(engine, expire_on_commit=False)
        operations = OperationsRepository(factory)
        snapshot = await operations.ensure_asset_snapshot(release_id="historical-release", release_version="v1", map_manifest={"points": [], "events": [{"id": "old", "review_status": "reviewed"}]}, actor_id="publisher")
        await SqlEventRepository(factory).review("old", ReviewStatus.PENDING, reviewer_id="reviewer", review_note="恢复待复核")
        async with factory() as session:
            stored = dict((await session.execute(sa.text("SELECT * FROM wu_asset_versions"))).mappings().one())
        for field in ("map_manifest_json", "map_manifest_sha256", "graph_manifest_sha256", "knowledge_release_id", "created_by"):
            assert stored[field] == snapshot[field]
    finally:
        await engine.dispose()
