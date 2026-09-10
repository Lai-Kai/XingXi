from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.gateway.routers import research_projects


@pytest.fixture()
def project_client(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'projects.db'}",
        poolclass=NullPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE wu_source_documents ("
                    "id VARCHAR(255) PRIMARY KEY, title VARCHAR(255) NOT NULL, "
                    "edition VARCHAR(255) NOT NULL, source_type VARCHAR(64) NOT NULL, "
                    "source_level VARCHAR(8) NOT NULL, source_institution VARCHAR(255) NOT NULL, "
                    "status VARCHAR(32) NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "CREATE TABLE wu_project_documents ("
                    "project_id VARCHAR(255) NOT NULL, document_id VARCHAR(255) NOT NULL, "
                    "added_by VARCHAR(255) NOT NULL, added_at TIMESTAMP NOT NULL, "
                    "PRIMARY KEY(project_id, document_id), "
                    "FOREIGN KEY(project_id) REFERENCES wu_research_projects(id) ON DELETE CASCADE, "
                    "FOREIGN KEY(document_id) REFERENCES wu_source_documents(id) ON DELETE RESTRICT)"
                )
            )

    # The project table is created lazily by the router, so create it before
    # the association table with the same schema used in production.
    async def _ordered_setup() -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE wu_research_projects ("
                    "id VARCHAR(255) PRIMARY KEY, owner_id VARCHAR(255) NOT NULL, "
                    "name VARCHAR(255) NOT NULL, archived BOOLEAN NOT NULL DEFAULT 0, "
                    "created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"
                )
            )
        await _setup()

    asyncio.run(_ordered_setup())
    monkeypatch.setattr(research_projects, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(research_projects, "_user_id", AsyncMock(return_value="researcher-1"))
    app = FastAPI()
    app.include_router(research_projects.router)
    yield TestClient(app), session_factory
    asyncio.run(engine.dispose())


def test_project_workspace_manages_documents_and_records(project_client) -> None:
    client, session_factory = project_client

    created = client.post("/api/research-projects", json={"name": "吴郡人物研究"})
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert client.get("/api/research-projects").json()[0]["document_count"] == 0

    async def _insert_document() -> None:
        async with session_factory() as session:
            await session.execute(text("INSERT INTO wu_source_documents (id,title,edition,source_type,source_level,source_institution,status) VALUES ('document-1','吴郡图经续记','明抄本','gazetteer','A','测试馆','registered')"))
            await session.commit()

    asyncio.run(_insert_document())
    attached = client.post(
        f"/api/research-projects/{project_id}/documents",
        json={"document_id": "document-1"},
    )
    assert attached.status_code == 201

    project = client.get(f"/api/research-projects/{project_id}").json()
    assert project["document_count"] == 1
    documents = client.get(f"/api/research-projects/{project_id}/documents").json()
    assert documents == [
        {
            "id": "document-1",
            "title": "吴郡图经续记",
            "edition": "明抄本",
            "source_type": "gazetteer",
            "source_level": "A",
            "source_institution": "测试馆",
            "status": "registered",
            "added_at": documents[0]["added_at"],
        }
    ]

    record = client.post(
        f"/api/research-projects/{project_id}/records",
        json={"kind": "question", "content": "范仲淹与木渎有什么关系？"},
    )
    assert record.status_code == 201
    record_id = record.json()["id"]
    assert client.get(f"/api/research-projects/{project_id}/records").json()[0]["kind"] == "question"

    renamed = client.patch(
        f"/api/research-projects/{project_id}",
        json={"name": "木渎人物关系研究"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "木渎人物关系研究"

    assert client.delete(f"/api/research-projects/{project_id}/records/{record_id}").status_code == 204
    assert client.delete(f"/api/research-projects/{project_id}/documents/document-1").status_code == 204
    assert client.get(f"/api/research-projects/{project_id}").json()["document_count"] == 0


def test_project_responses_use_json_booleans(project_client) -> None:
    client, _session_factory = project_client

    created = client.post("/api/research-projects", json={"name": "木渎古桥研究"})
    assert created.status_code == 201
    assert created.json()["archived"] is False

    project_id = created.json()["id"]
    listed = client.get("/api/research-projects")
    assert listed.status_code == 200
    assert listed.json()[0]["archived"] is False

    detail = client.get(f"/api/research-projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["archived"] is False

    archived = client.patch(
        f"/api/research-projects/{project_id}",
        json={"archived": True},
    )
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
