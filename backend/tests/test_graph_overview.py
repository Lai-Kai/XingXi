"""Release, authorization, pagination and discovery use the real SQL/HTTP path."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import event, inspect, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway.routers import knowledge_graph
from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture import overview_repository
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
@pytest.mark.parametrize(
    "target,values",
    [
        (WuEntityRow, {"review_status": "rejected"}),
        (WuEntityRow, {"updated_at": datetime.now(UTC) + timedelta(days=1)}),
        (SourceDocumentRow, {"authorization_valid_until": datetime.now(UTC) - timedelta(days=1)}),
        (EvidenceRow, {"review_status": "pending"}),
        (TextChunkRow, {"review_status": "disputed"}),
    ],
)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["overview", "directory"])
async def test_graph_reads_load_only_linked_evidence_metadata(overview_db, view):
    client, factory = overview_db
    # A large text corpus must not be hydrated just to show a small graph.
    async with factory.begin() as session:
        for i in range(40):
            key = f"unlinked-{i}"
            session.add(TextChunkRow(id=key, document_id="0", original_text="正文" * 5000, normalized_text="正文" * 5000, page_start=2, page_end=2, review_status="reviewed"))
            await session.flush()
            session.add(EvidenceRow(id=key, document_id="0", chunk_id=key, quote="引文" * 5000, source_level="A", review_status="reviewed"))
            session.add(KnowledgeReleaseItemRow(release_id="release", ordinal=100 + i, document_id="0", source_file_id="file", chunk_set_id="set", chunk_id=key, content_sha256="b" * 64, cleaned_page_ids_json="[]"))

    loaded_evidence = {}
    loaded_chunks = {}

    def track_evidence(row, _context):
        loaded_evidence[row.id] = inspect(row).unloaded

    def track_chunk(row, _context):
        loaded_chunks[row.id] = inspect(row).unloaded

    event.listen(EvidenceRow, "load", track_evidence)
    event.listen(TextChunkRow, "load", track_chunk)
    try:
        response = await client.get(f"/api/knowledge-graph/{view}")
    finally:
        event.remove(EvidenceRow, "load", track_evidence)
        event.remove(TextChunkRow, "load", track_chunk)

    assert response.status_code == 200, response.text
    assert response.json()["total_edges"] == 2
    assert set(loaded_evidence) == {str(i) for i in range(7)}
    assert all("quote" in unloaded for unloaded in loaded_evidence.values())
    assert all({"original_text", "normalized_text"} <= unloaded for unloaded in loaded_chunks.values())


@pytest.mark.asyncio
async def test_shared_source_authorization_is_checked_once_per_request(overview_db, monkeypatch):
    client, factory = overview_db
    async with factory.begin() as session:
        session.add(TextChunkRow(id="shared", document_id="0", original_text="补充", normalized_text="补充", page_start=2, page_end=2, review_status="reviewed"))
        await session.flush()
        session.add(EvidenceRow(id="shared", document_id="0", chunk_id="shared", quote="补充", source_level="A", review_status="reviewed"))
        session.add(KnowledgeReleaseItemRow(release_id="release", ordinal=100, document_id="0", source_file_id="file", chunk_set_id="set", chunk_id="shared", content_sha256="b" * 64, cleaned_page_ids_json="[]"))
        await session.flush()
        session.add(WuEntityEvidenceRow(entity_id="0", evidence_id="shared"))

    calls = []
    evaluate = overview_repository.evaluate_source_access

    def track_access(document, **kwargs):
        calls.append(document.id)
        return evaluate(document, **kwargs)

    monkeypatch.setattr(overview_repository, "evaluate_source_access", track_access)
    first = await client.get("/api/knowledge-graph/overview")
    assert first.status_code == 200, first.text
    assert {e["id"] for e in first.json()["edges"]} == {"a", "b"}
    assert calls.count("0") == 1

    async with factory.begin() as session:
        await session.execute(update(SourceDocumentRow).where(SourceDocumentRow.id == "0").values(authorization_status="revoked"))
    following = await client.get("/api/knowledge-graph/directory")
    assert following.status_code == 200, following.text
    assert "0" not in {n["id"] for n in following.json()["nodes"]}
    assert calls.count("0") == 2


@pytest.mark.asyncio
async def test_working_groups_include_unpublished_review_chains_without_publishing(overview_db, monkeypatch):
    client, factory = overview_db

    async def admin(request, **kwargs):
        return SimpleNamespace(id="admin", system_role="admin")

    monkeypatch.setattr(knowledge_graph, "require_admin_user", admin)
    async with factory.begin() as session:
        # A new extracted chain has not entered the active manifest. Its endpoint
        # entities remain pending even after the relation receives human review.
        await session.execute(update(WuEntityRow).where(WuEntityRow.id == "7").values(release_id=None, review_status="pending"))
        await session.execute(update(WuRelationRow).where(WuRelationRow.id == "e").values(release_id=None, review_status="pending"))
    params = {"view": "working", "review_status": "reviewed"}
    headers = {"x-role": "admin"}
    before = (await client.get("/api/knowledge-graph/overview", params=params, headers=headers)).json()
    assert "e" not in {e["id"] for e in before["edges"]}
    response = await client.patch("/api/knowledge-graph/relations/e/review", headers=headers, json={"review_status": "reviewed", "expected_status": "pending"})
    assert response.status_code == 200, response.text
    page = (await client.get("/api/knowledge-graph/overview", params=params, headers=headers)).json()
    assert page["view"] == "working" and page["release_id"] is None
    assert "e" in {e["id"] for e in page["edges"]}
    assert "7" in {n["id"] for n in page["nodes"]}
    assert any(group["total_nodes"] >= 3 for group in page["components"])
    directory = (await client.get("/api/knowledge-graph/directory", params=params, headers=headers)).json()
    assert "7" in {n["id"] for n in directory["nodes"]}
    assert "e" not in {e["id"] for e in (await client.get("/api/knowledge-graph/overview")).json()["edges"]}
    # Corrections also recompute membership; approving again restores the chain
    # without inserting duplicate graph facts or publishing a new edition.
    rejected = await client.patch("/api/knowledge-graph/relations/e/review", headers=headers, json={"review_status": "rejected", "expected_status": "reviewed", "review_note": "证据待重核"})
    assert rejected.status_code == 200, rejected.text
    hidden = (await client.get("/api/knowledge-graph/overview", params={"view": "working"}, headers=headers)).json()
    assert "7" not in {n["id"] for n in hidden["nodes"]}
    restored = await client.patch("/api/knowledge-graph/relations/e/review", headers=headers, json={"review_status": "reviewed", "expected_status": "rejected", "review_note": "已重新核验原文"})
    assert restored.status_code == 200, restored.text
    shown = (await client.get("/api/knowledge-graph/overview", params=params, headers=headers)).json()
    assert [e["id"] for e in shown["edges"]].count("e") == 1
    async with factory() as session:
        assert (await session.get(KnowledgeReleaseStateRow, "active")).active_release_id == "release"
        assert (await session.scalars(select(KnowledgeReleaseRow.id))).all() == ["release"]
        assert (await session.get(KnowledgeReleaseRow, "release")).manifest_sha256 == "a" * 64
        assert len((await session.scalars(select(KnowledgeReleaseItemRow.chunk_id))).all()) == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["overview", "directory"])
async def test_working_graph_is_admin_review_metadata_even_without_an_active_release(overview_db, view):
    client, factory = overview_db
    async with factory.begin() as session:
        await session.execute(update(KnowledgeReleaseStateRow).values(active_release_id=None))
        await session.execute(update(SourceDocumentRow).where(SourceDocumentRow.id == "7").values(authorization_status="unconfirmed", visibility_scope="internal", authorized_uses_json="[]"))
    result = await client.get(f"/api/knowledge-graph/{view}", params={"view": "working"}, headers={"x-role": "admin"})
    assert result.status_code == 200, result.text
    page = result.json()
    assert page["view"] == "working" and page["release_id"] is None
    assert "7" in {n["id"] for n in page["nodes"]}
    assert page["authorization_pending_sources"] == 1
    assert all("quote" not in evidence for evidence in page["evidence"])
    assert (await client.get(f"/api/knowledge-graph/{view}", params={"view": "working"})).status_code == 403
    assert (await client.get(f"/api/knowledge-graph/{view}")).json()["nodes"] == []
    async with factory() as session:
        assert (await session.get(SourceDocumentRow, "7")).authorization_status == "unconfirmed"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["revoked", "expired"])
async def test_working_graph_excludes_restricted_sources_and_invalidates_cursors(overview_db, status):
    client, factory = overview_db
    params = {"view": "working", "max_edges": 1}
    headers = {"x-role": "admin"}
    first = (await client.get("/api/knowledge-graph/overview", params=params, headers=headers)).json()
    async with factory.begin() as session:
        await session.execute(update(SourceDocumentRow).where(SourceDocumentRow.id == "2").values(authorization_status=status))
    page = (await client.get("/api/knowledge-graph/overview", params={"view": "working"}, headers=headers)).json()
    assert "2" not in {n["id"] for n in page["nodes"]}
    assert "b" not in {e["id"] for e in page["edges"]}
    response = await client.get("/api/knowledge-graph/overview", params={**params, "cursor": first["next_cursor"]}, headers=headers)
    assert response.status_code == 409
    assert (await client.get("/api/knowledge-graph/overview", params={"view": "published", "cursor": first["next_cursor"]}, headers=headers)).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        {"authorized_uses_json": '["public_quote"]'},
        {"authorization_valid_until": datetime.now(UTC) - timedelta(days=1)},
        {"authorization_valid_from": datetime.now(UTC) + timedelta(days=1)},
        {"authorization_status": "unconfirmed", "visibility_scope": "public", "authorized_uses_json": "[]"},
        {"authorization_status": "unconfirmed", "visibility_scope": "internal", "authorized_uses_json": "[]", "authorization_valid_until": datetime.now(UTC) + timedelta(days=1)},
    ],
)
async def test_working_review_inspection_does_not_override_other_source_policies(overview_db, values):
    client, factory = overview_db
    async with factory.begin() as session:
        await session.execute(update(SourceDocumentRow).where(SourceDocumentRow.id == "2").values(**values))
    response = await client.get("/api/knowledge-graph/overview", params={"view": "working"}, headers={"x-role": "admin"})
    assert response.status_code == 200, response.text
    page = response.json()
    assert "2" not in {n["id"] for n in page["nodes"]}
    assert "b" not in {e["id"] for e in page["edges"]}
    assert page["authorization_pending_sources"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["internal", "public"])
async def test_internal_graph_retains_only_evidence_bound_earlier_internal_facts(overview_db, scope):
    client, factory = overview_db
    async with factory.begin() as session:
        await session.execute(update(KnowledgeReleaseRow).where(KnowledgeReleaseRow.id == "release").values(scope=scope, version_number=2))
        for key, version in [("earlier", 1), ("future", 3)]:
            session.add(KnowledgeReleaseRow(id=key, version_number=version, release_notes="test", status="ready", scope="internal", manifest_sha256=key[0] * 64, created_by="admin", created_at=datetime.now(UTC)))
        await session.flush()
        await session.execute(update(WuEntityRow).where(WuEntityRow.id.in_(["0", "7"])).values(release_id="earlier"))
        await session.execute(update(WuEntityRow).where(WuEntityRow.id == "2").values(release_id="future"))
        await session.execute(update(WuRelationRow).where(WuRelationRow.id == "a").values(release_id="earlier"))
    response = await client.get("/api/knowledge-graph/directory", headers={"x-role": "admin"})
    assert response.status_code == 200, response.text
    ids = {node["id"] for node in response.json()["nodes"]}
    assert ("0" in ids) is (scope == "internal")
    assert "2" not in ids  # A later edition cannot leak into a frozen Run.
    assert "7" not in ids  # Earlier facts still need exact current-manifest Evidence.
