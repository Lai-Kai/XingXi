"""Release, authorization, pagination and discovery use the real SQL/HTTP path."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway.routers import knowledge_graph
from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture.model import (
    WU_CULTURE_TABLES,
    EvidenceRow,
    KnowledgeReleaseItemRow,
    KnowledgeReleaseRow,
    KnowledgeReleaseStateRow,
    SourceDocumentRow,
    TextChunkRow,
    WuEntityEvidenceRow,
    WuEntityRow,
    WuRelationEvidenceRow,
    WuRelationRow,
)


@pytest_asyncio.fixture
async def overview_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'overview.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=WU_CULTURE_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory.begin() as session:
        session.add(KnowledgeReleaseRow(id="release", version_number=1, release_notes="test", status="active", scope="public", manifest_sha256="a" * 64, created_by="admin", created_at=now))
        await session.flush()
        session.add(KnowledgeReleaseStateRow(id="active", active_release_id="release", state_version=1))
        for i, (name, kind, status) in enumerate(
            [
                ("康熙帝", "person", "reviewed"),
                ("邓尉山", "place", "reviewed"),
                ("顾况", "person", "reviewed"),
                ("木渎", "place", "reviewed"),
                ("古建筑", "building", "reviewed"),
                ("待审人物", "person", "pending"),
                ("无权主体", "place", "reviewed"),
                ("未发布", "place", "reviewed"),
            ]
        ):
            key = str(i)
            session.add(
                SourceDocumentRow(
                    id=key,
                    title=name,
                    source_type="gazetteer",
                    source_level="A",
                    copyright_status="public_domain",
                    authorization_status="active",
                    authorization_basis="测试授权",
                    visibility_scope="public",
                    authorized_uses_json='["public_quote","internal_processing"]' if i != 6 else '["internal_processing"]',
                )
            )
            await session.flush()
            session.add(TextChunkRow(id=key, document_id=key, original_text=name, normalized_text=name, page_start=1, page_end=1, review_status="reviewed"))
            await session.flush()
            session.add(EvidenceRow(id=key, document_id=key, chunk_id=key, quote=name, source_level="A", review_status="reviewed"))
            session.add(WuEntityRow(id=key, canonical_name=name, entity_type=kind, dynasty="清" if i < 2 else "唐", review_status=status, release_id="release", created_at=now - timedelta(days=1), updated_at=now - timedelta(days=1)))
            await session.flush()
            session.add(WuEntityEvidenceRow(entity_id=key, evidence_id=key))
            if i != 7:
                # Only the manifest identity columns are needed by graph reads.
                session.add(KnowledgeReleaseItemRow(release_id="release", ordinal=i, document_id=key, source_file_id="file", chunk_set_id="set", chunk_id=key, content_sha256="b" * 64, cleaned_page_ids_json="[]"))
        for key, subject, obj, status in [("a", "0", "1", "reviewed"), ("b", "2", "3", "reviewed"), ("c", "5", "1", "pending"), ("d", "0", "6", "reviewed"), ("e", "0", "7", "reviewed")]:
            session.add(WuRelationRow(id=key, subject_id=subject, object_id=obj, relation_type="visited", confidence=0.9, review_status=status, release_id="release", created_at=now - timedelta(days=1), updated_at=now - timedelta(days=1)))
            await session.flush()
            session.add(WuRelationEvidenceRow(relation_id=key, evidence_id=subject))
    app = FastAPI()

    async def user(request):
        return SimpleNamespace(id="reader", system_role=request.headers.get("x-role", "user"))

    monkeypatch.setattr(knowledge_graph, "get_current_user_from_request", user)
    monkeypatch.setattr(knowledge_graph, "get_session_factory", lambda: factory)
    app.include_router(knowledge_graph.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        yield client, factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_overview_discovers_disconnected_components_and_paginates(overview_db):
    client, _ = overview_db
    response = await client.get("/api/knowledge-graph/overview", params={"max_edges": 1, "max_nodes": 2})
    assert response.status_code == 200, response.text
    page = response.json()
    assert (page["total_nodes"], page["total_edges"], page["returned_nodes"], page["returned_edges"]) == (4, 2, 2, 1)
    assert page["truncated"] and page["next_cursor"]
    assert len(page["components"]) == 2
    following = (await client.get("/api/knowledge-graph/overview", params={"max_edges": 1, "max_nodes": 2, "cursor": page["next_cursor"]})).json()
    assert {e["id"] for e in page["edges"] + following["edges"]} == {"a", "b"}
    assert not following["truncated"]
    for result in (page, following):
        ids = {n["id"] for n in result["nodes"]}
        assert all(e["subject_id"] in ids and e["object_id"] in ids and e["evidence_ids"] for e in result["edges"])


@pytest.mark.asyncio
async def test_overview_security_directory_and_admin_filters(overview_db):
    client, factory = overview_db
    page = (await client.get("/api/knowledge-graph/overview")).json()
    assert {n["id"] for n in page["nodes"]} == {"0", "1", "2", "3"}
    directory = (await client.get("/api/knowledge-graph/directory", params={"entity_type": "building"})).json()
    assert [(n["canonical_name"], n["has_relations"]) for n in directory["nodes"]] == [("古建筑", False)]
    assert (await client.get("/api/knowledge-graph/overview", params={"review_status": "pending"})).status_code == 403
    admin = (await client.get("/api/knowledge-graph/overview", headers={"x-role": "admin"}, params={"review_status": "pending"})).json()
    assert [e["id"] for e in admin["edges"]] == ["c"]
    async with factory.begin() as session:
        await session.execute(update(SourceDocumentRow).where(SourceDocumentRow.id == "2").values(authorization_status="revoked"))
    assert [e["id"] for e in (await client.get("/api/knowledge-graph/overview")).json()["edges"]] == ["a"]


@pytest.mark.asyncio
async def test_cursor_binds_filters_release_and_visible_data(overview_db):
    client, factory = overview_db
    first = (await client.get("/api/knowledge-graph/overview", params={"max_edges": 1})).json()
    assert (await client.get("/api/knowledge-graph/overview", params={"cursor": first["next_cursor"], "scope": "people"})).status_code == 409
    assert (await client.get("/api/knowledge-graph/overview", params={"cursor": "garbage"})).status_code == 400
    async with factory.begin() as session:
        await session.execute(update(KnowledgeReleaseRow).values(scope="internal"))
    assert (await client.get("/api/knowledge-graph/overview")).json()["nodes"] == []
    async with factory.begin() as session:
        await session.execute(update(KnowledgeReleaseStateRow).values(active_release_id=None))
    assert (await client.get("/api/knowledge-graph/overview")).json()["release_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("target,values", [
    (WuEntityRow, {"review_status": "rejected"}),
    (WuEntityRow, {"updated_at": datetime.now(UTC) + timedelta(days=1)}),
    (SourceDocumentRow, {"authorization_valid_until": datetime.now(UTC) - timedelta(days=1)}),
    (EvidenceRow, {"review_status": "pending"}),
    (TextChunkRow, {"review_status": "disputed"}),
])
async def test_ordinary_reads_fail_closed_on_each_visibility_gate(overview_db, target, values):
    client, factory = overview_db
    first = (await client.get("/api/knowledge-graph/overview", params={"max_edges": 1})).json()
    async with factory.begin() as session:
        await session.execute(update(target).where(target.id == "2").values(**values))
    result = (await client.get("/api/knowledge-graph/overview")).json()
    assert [e["id"] for e in result["edges"]] == ["a"]
    assert all(n["id"] != "2" for n in result["nodes"])
    assert (await client.get("/api/knowledge-graph/overview", params={"cursor": first["next_cursor"]})).status_code == 409


@pytest.mark.asyncio
async def test_component_local_filters_and_directory_pagination(overview_db):
    client, _ = overview_db
    page = (await client.get("/api/knowledge-graph/overview", params={"component_id": "2"})).json()
    assert {n["id"] for n in page["nodes"]} == {"2", "3"}
    assert len(page["components"]) == 2
    local = (await client.get("/api/knowledge-graph/overview", params={"center": "2"})).json()
    assert local["edges"] == page["edges"]
    filtered = (await client.get("/api/knowledge-graph/overview", params={"scope": "people"})).json()
    assert filtered["total_nodes"] == filtered["total_edges"] == 0
    assert (await client.get("/api/knowledge-graph/overview", params={"max_nodes": 1})).status_code == 422
    assert (await client.get("/api/knowledge-graph/overview", params={"release_id": "another"})).status_code == 409
    seen = []
    cursor = None
    while True:
        response = await client.get("/api/knowledge-graph/directory", params={"max_nodes": 2, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200, response.text
        value = response.json()
        seen.extend(n["id"] for n in value["nodes"])
        cursor = value["next_cursor"]
        if not cursor:
            break
    assert seen == ["0", "1", "2", "3", "4"]
    directory = (await client.get("/api/knowledge-graph/directory", params={"name": "木", "dynasty": "唐", "entity_type": "place"})).json()
    assert [n["id"] for n in directory["nodes"]] == ["3"]
