"""Uploaded and existing documents produce cumulative, evidence-bound draft graphs."""

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture.releases import RollbackReleaseRequest

from app.gateway.ingestion_worker import IngestionWorker
from app.gateway.routers import knowledge_graph, source_documents
from deerflow.object_storage import LocalObjectStorage
from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow, SqlObjectMetadataRepository
from deerflow.persistence.wu_culture import (
    WU_CULTURE_TABLES,
    KnowledgeReleaseRow,
    SqlEvidenceRepository,
    SqlIngestionJobRepository,
    SqlKnowledgeReleaseRepository,
    SqlOcrRepository,
    SqlParsedDocumentRepository,
    SqlSourceDocumentRepository,
    SqlSourceFileRepository,
    SqlStructuredChunkRepository,
    SqlTextCleaningRepository,
)
from deerflow.persistence.wu_culture.graph_repository import SqlKnowledgeGraphRepository
from deerflow.persistence.wu_culture.model import SourceDocumentRow, WuEntityRow, WuRelationRow


@pytest_asyncio.fixture
async def pipeline(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'pipeline.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[*WU_CULTURE_TABLES, ObjectMetadataRow.__table__]))
        await connection.execute(
            text("""CREATE TABLE wu_asset_versions (
            id TEXT PRIMARY KEY, knowledge_release_id TEXT UNIQUE NOT NULL,
            knowledge_release_version TEXT NOT NULL, graph_manifest_sha256 TEXT NOT NULL,
            map_manifest_sha256 TEXT NOT NULL, map_manifest_json TEXT, entity_count INTEGER NOT NULL,
            map_point_count INTEGER NOT NULL, created_by TEXT NOT NULL, created_at DATETIME NOT NULL
        )""")
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sources = SqlSourceDocumentRepository(factory)
    files = SqlSourceFileRepository(factory)
    jobs = SqlIngestionJobRepository(factory)
    storage = LocalObjectStorage(tmp_path / "objects")
    config = SimpleNamespace(ingestion=SimpleNamespace(max_concurrent_jobs=2, lease_seconds=60, auto_publish_internal_release=True))
    worker = IngestionWorker(
        job_repository=jobs,
        source_file_repository=files,
        source_document_repository=sources,
        parsed_repository=SqlParsedDocumentRepository(factory),
        ocr_repository=SqlOcrRepository(factory),
        cleaning_repository=SqlTextCleaningRepository(factory),
        chunk_repository=SqlStructuredChunkRepository(factory),
        evidence_repository=SqlEvidenceRepository(factory),
        graph_repository=SqlKnowledgeGraphRepository(factory),
        object_storage=storage,
        object_metadata_repository=SqlObjectMetadataRepository(factory),
        corpus_config=None,
        app_config=config,
    )

    async def admin_id(request):
        if request.headers.get("x-role") == "user":
            raise HTTPException(status_code=403)
        return "admin"

    async def user(request):
        return SimpleNamespace(id="admin", system_role=request.headers.get("x-role", "admin"))

    async def map_manifest(_release):
        return {"points": [], "routes": []}

    monkeypatch.setattr(source_documents, "_admin_id", admin_id)
    monkeypatch.setattr(knowledge_graph, "get_current_user_from_request", user)
    monkeypatch.setattr(knowledge_graph, "get_session_factory", lambda: factory)
    monkeypatch.setattr("deerflow.persistence.engine.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.gateway.routers.map_points.build_release_map_manifest", map_manifest)
    app = FastAPI()
    app.dependency_overrides[source_documents.get_source_document_repository] = lambda: sources
    app.dependency_overrides[source_documents.get_source_file_repository] = lambda: files
    app.dependency_overrides[source_documents.get_optional_ingestion_job_repository] = lambda: jobs
    app.dependency_overrides[source_documents.get_ingestion_job_repository] = lambda: jobs
    app.dependency_overrides[source_documents.get_source_object_storage] = lambda: storage
    app.dependency_overrides[source_documents.get_source_upload_staging_dir] = lambda: tmp_path / "staging"
    app.include_router(source_documents.router)
    app.include_router(knowledge_graph.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        yield client, worker, factory, sources
    await engine.dispose()


async def upload(client, title, body, *, generate=True):
    response = await client.post(
        "/api/source-documents",
        json={
            "title": title,
            "edition": "测试版",
            "source_institution": "测试馆",
            "source_type": "gazetteer",
            "source_level": "B",
            "holder": "测试资料组",
        },
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]
    response = await client.post(f"/api/source-documents/{document_id}/files", data={"generate_graph": str(generate).lower()}, files={"files": (f"{title}.txt", body.encode(), "text/plain")})
    assert response.status_code == 200, response.text
    assert response.json()["success_count"] == 1, response.text
    return document_id, response.json()["items"][0]["file"]["id"]


async def drain(worker):
    for _ in range(20):
        if not await worker.run_once():
            return
    pytest.fail("ingestion worker did not settle")


@pytest.mark.asyncio
async def test_uploads_automatically_build_and_extend_the_internal_graph(pipeline):
    client, worker, factory, sources = pipeline
    first_document, _ = await upload(client, "桥梁志", "永安桥位于木渎镇。")
    await drain(worker)
    first = (await client.get("/api/knowledge-graph/overview")).json()
    assert {"永安桥", "木渎镇"} <= {node["canonical_name"] for node in first["nodes"]}
    policy = await sources.get(first_document)
    assert [use.value for use in policy.authorized_uses] == ["internal_processing"]
    assert policy.visibility_scope.value == "internal"
    assert len(await sources.list_authorization_events(first_document)) == 1
    assert all(node["review_status"] == "pending" for node in first["nodes"])

    # Existing seed records may be bound to the previous internal edition.
    async with factory.begin() as session:
        await session.execute(update(WuEntityRow).values(release_id=first["release_id"]))
        await session.execute(update(WuRelationRow).values(release_id=first["release_id"]))
    await upload(client, "书院志", "清晖书院位于澄溪镇。")
    await drain(worker)
    second = (await client.get("/api/knowledge-graph/overview")).json()
    assert second["release_id"] != first["release_id"]
    assert {node["id"] for node in first["nodes"]} <= {node["id"] for node in second["nodes"]}
    assert {"清晖书院", "澄溪镇"} <= {node["canonical_name"] for node in second["nodes"]}
    assert second["total_edges"] > first["total_edges"]
    graph = SqlKnowledgeGraphRepository(factory)
    assert await graph.resolve_entities(first["nodes"][0]["id"], release_id=second["release_id"])
    assert (await client.get("/api/knowledge-graph/overview", headers={"x-role": "user"})).json()["nodes"] == []
    async with factory() as session:
        asset = (await session.execute(text("SELECT entity_count FROM wu_asset_versions WHERE knowledge_release_id=:id"), {"id": second["release_id"]})).scalar_one()
        assert asset == second["total_nodes"]
        count = (await session.execute(select(func.count()).select_from(KnowledgeReleaseRow))).scalar_one()
    await worker.run_once()
    async with factory() as session:
        assert (await session.execute(select(func.count()).select_from(KnowledgeReleaseRow))).scalar_one() == count

    # Reads continue to recheck source permission after automatic generation.
    async with factory.begin() as session:
        await session.execute(update(SourceDocumentRow).where(SourceDocumentRow.id == first_document).values(authorization_status="revoked"))
    remaining = (await client.get("/api/knowledge-graph/overview")).json()
    assert "永安桥" not in {node["canonical_name"] for node in remaining["nodes"]}


@pytest.mark.asyncio
async def test_existing_upload_can_generate_without_reupload_or_manual_review(pipeline):
    client, worker, factory, sources = pipeline
    document_id, file_id = await upload(client, "已有文献", "永安桥位于木渎镇。", generate=False)
    await drain(worker)
    assert (await client.get("/api/knowledge-graph/overview")).json()["nodes"] == []
    url = f"/api/source-documents/{document_id}/files/{file_id}/generate-graph"
    assert (await client.post(url, headers={"x-role": "user"})).status_code == 403
    response = await client.post(url)
    assert response.status_code == 200, response.text
    await drain(worker)
    assert (await client.get("/api/knowledge-graph/overview")).json()["total_nodes"] > 0
    repeated = await client.post(url)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == response.json()["id"]
    assert len(await sources.list_authorization_events(document_id)) == 1
    async with factory.begin() as session:
        await session.execute(update(SourceDocumentRow).where(SourceDocumentRow.id == document_id).values(authorization_status="revoked"))
    assert (await client.post(url)).status_code == 409
    assert (await sources.get(document_id)).authorization_status.value == "revoked"


@pytest.mark.asyncio
async def test_idle_worker_picks_up_late_permission_without_hydrating_all_text(pipeline, monkeypatch):
    client, worker, factory, _ = pipeline
    document_id, _ = await upload(client, "稍后允许处理", "清晖书院位于澄溪镇。", generate=False)
    await drain(worker)

    async def no_text_scan():
        pytest.fail("idle reconciliation must not load every ChunkSet's text")

    monkeypatch.setattr(worker._chunks, "list_all", no_text_scan)
    response = await client.put(
        f"/api/source-documents/{document_id}/authorization",
        json={
            "copyright_status": "unknown",
            "authorization_status": "active",
            "authorization_basis": "管理员允许内部处理",
            "visibility_scope": "internal",
            "authorized_uses": ["internal_processing"],
            "change_reason": "内部图谱生成",
        },
    )
    assert response.status_code == 200, response.text
    worker._last_working_sync = 0
    assert await worker.run_once() is False
    page = (await client.get("/api/knowledge-graph/overview")).json()
    assert {"清晖书院", "澄溪镇"} <= {node["canonical_name"] for node in page["nodes"]}
    release = await SqlKnowledgeReleaseRepository(factory).get_active()
    assert release.scope == "internal"


@pytest.mark.asyncio
async def test_graph_action_retries_a_failed_extraction_without_duplicate_facts(pipeline, monkeypatch):
    client, worker, factory, _ = pipeline
    document_id, file_id = await upload(client, "重试文献", "清晖书院位于澄溪镇。", generate=False)
    await drain(worker)
    ingest = worker._graph.ingest_chunk

    async def fail_once(**_kwargs):
        raise RuntimeError("temporary graph extraction failure")

    monkeypatch.setattr(worker._graph, "ingest_chunk", fail_once)
    url = f"/api/source-documents/{document_id}/files/{file_id}/generate-graph"
    response = await client.post(url)
    await drain(worker)
    job = await worker._jobs.get(response.json()["id"])
    assert job.status.value == "failed"
    monkeypatch.setattr(worker._graph, "ingest_chunk", ingest)
    retry = await client.post(url)
    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == job.id
    assert retry.json()["status"] == "pending"
    await drain(worker)
    assert (await worker._jobs.get(job.id)).status.value == "awaiting_review"
    async with factory() as session:
        names = (await session.execute(select(WuEntityRow.canonical_name))).scalars().all()
    assert names.count("清晖书院") == 1


@pytest.mark.asyncio
async def test_failed_internal_release_is_retried_in_place_when_graph_job_retries(pipeline, monkeypatch):
    from deerflow.persistence.wu_culture import SqlFullTextRepository

    client, worker, factory, _ = pipeline
    index_release = SqlFullTextRepository.index_release
    should_fail = True

    async def fail_first_index(self, *args, **kwargs):
        nonlocal should_fail
        if should_fail:
            should_fail = False
            raise RuntimeError("temporary index preparation failure")
        return await index_release(self, *args, **kwargs)

    monkeypatch.setattr(SqlFullTextRepository, "index_release", fail_first_index)
    document_id, file_id = await upload(client, "索引重试文献", "永安桥位于木渎镇。")
    for _ in range(20):
        await worker.run_once()
        jobs = await worker._jobs.list_for_source_file(file_id)
        if jobs[0].status.value == "failed":
            break
    else:
        pytest.fail("expected index preparation failure")
    async with factory() as session:
        failed_id = (await session.execute(select(KnowledgeReleaseRow.id).where(KnowledgeReleaseRow.status == "failed"))).scalar_one()
    retry = await client.post(f"/api/source-documents/{document_id}/files/{file_id}/generate-graph")
    assert retry.status_code == 200, retry.text
    await drain(worker)
    assert (await worker._jobs.get(retry.json()["id"])).status.value == "awaiting_review"
    active = await SqlKnowledgeReleaseRepository(factory).get_active()
    assert active.id == failed_id
    assert active.preparation_attempts == 2
    async with factory() as session:
        assert (await session.execute(select(func.count()).select_from(KnowledgeReleaseRow))).scalar_one() == 1


@pytest.mark.asyncio
async def test_idle_reconciliation_never_replaces_an_active_public_edition(pipeline):
    client, worker, factory, _ = pipeline
    await upload(client, "已有内部图谱", "清晖书院位于澄溪镇。")
    await drain(worker)
    previous = await SqlKnowledgeReleaseRepository(factory).get_active()
    # Simulate the administrator completing public review/publication. The
    # worker must leave that choice authoritative on all subsequent idle ticks.
    async with factory.begin() as session:
        await session.execute(update(KnowledgeReleaseRow).where(KnowledgeReleaseRow.id == previous.id).values(scope="public"))
    worker._last_working_sync = 0
    await worker.run_once()
    active = await SqlKnowledgeReleaseRepository(factory).get_active()
    assert active.id == previous.id
    assert active.scope == "public"
    await upload(client, "公开版后的新文献", "永安桥位于木渎镇。")
    await drain(worker)
    assert (await SqlKnowledgeReleaseRepository(factory).get_active()).id == previous.id


@pytest.mark.asyncio
async def test_idle_reconciliation_preserves_an_administrator_rollback(pipeline):
    client, worker, factory, _ = pipeline
    await upload(client, "早期文献", "永安桥位于木渎镇。")
    await drain(worker)
    repository = SqlKnowledgeReleaseRepository(factory)
    first = await repository.get_active()
    await upload(client, "新文献", "清晖书院位于澄溪镇。")
    await drain(worker)
    state = await repository.get_state()
    await repository.rollback(RollbackReleaseRequest(target_release_id=first.id, expected_state_version=state.state_version, reason="管理员回滚核查"), actor_id="admin", changed_at=datetime.now(UTC))
    worker._last_working_sync = 0
    await worker.run_once()
    assert (await repository.get_active()).id == first.id
