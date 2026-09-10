from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.gateway.deps import require_business_capability
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/research-projects", tags=["research-projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ProjectArchive(BaseModel):
    archived: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)


class ResearchProjectResponse(BaseModel):
    id: str
    name: str
    archived: bool
    created_at: datetime
    updated_at: datetime
    document_count: int = Field(ge=0)


class ProjectDocument(BaseModel):
    document_id: str = Field(min_length=1, max_length=255)


class ProjectRecordKind(StrEnum):
    QUESTION = "question"
    NOTE = "note"
    CONCLUSION = "conclusion"


class ProjectRecordCreate(BaseModel):
    kind: ProjectRecordKind
    content: str = Field(min_length=1, max_length=10000)


class ProjectRecordUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


async def _user_id(request: Request) -> str:
    user = await require_business_capability(
        request,
        "project:manage",
        detail="This account role cannot manage research projects",
    )
    return str(user.id)


async def _session():
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Research projects require a SQL database")
    session = session_factory()
    await session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS wu_research_projects ("
            "id VARCHAR(255) PRIMARY KEY, owner_id VARCHAR(255) NOT NULL, "
            "name VARCHAR(255) NOT NULL, archived BOOLEAN NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"
        )
    )
    await session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS wu_project_records ("
            "id VARCHAR(255) PRIMARY KEY, project_id VARCHAR(255) NOT NULL, "
            "kind VARCHAR(32) NOT NULL, content TEXT NOT NULL, "
            "created_by VARCHAR(255) NOT NULL, created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL, "
            "FOREIGN KEY(project_id) REFERENCES wu_research_projects(id) ON DELETE CASCADE, "
            "CHECK(kind IN ('question','note','conclusion')))"
        )
    )
    await session.commit()
    return session


_PROJECT_SELECT = "SELECT p.id, p.name, p.archived, p.created_at, p.updated_at, (SELECT COUNT(*) FROM wu_project_documents pd WHERE pd.project_id=p.id) AS document_count FROM wu_research_projects p "


async def _owned_project(session, project_id: str, owner_id: str) -> dict:
    row = (
        (
            await session.execute(
                text(_PROJECT_SELECT + "WHERE p.id=:id AND p.owner_id=:owner"),
                {"id": project_id, "owner": owner_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Research project not found")
    return dict(row)


@router.get("", response_model=list[ResearchProjectResponse])
async def list_projects(request: Request) -> list[dict]:
    async with await _session() as session:
        rows = (await session.execute(text(_PROJECT_SELECT + "WHERE p.owner_id=:owner ORDER BY p.created_at DESC"), {"owner": await _user_id(request)})).mappings().all()
        return [dict(row) for row in rows]


@router.get("/{project_id}", response_model=ResearchProjectResponse)
async def get_project(project_id: str, request: Request) -> dict:
    async with await _session() as session:
        return await _owned_project(session, project_id, await _user_id(request))


@router.post("", response_model=ResearchProjectResponse, status_code=201)
async def create_project(body: ProjectCreate, request: Request) -> dict:
    now = datetime.now(UTC)
    project_id = f"project-{uuid4().hex}"
    name = body.name.strip()
    async with await _session() as session:
        await session.execute(
            text("INSERT INTO wu_research_projects (id, owner_id, name, archived, created_at, updated_at) VALUES (:id,:owner,:name,0,:created,:updated)"),
            {"id": project_id, "owner": await _user_id(request), "name": name, "created": now, "updated": now},
        )
        await session.commit()
    return {
        "id": project_id,
        "name": name,
        "archived": False,
        "created_at": now,
        "updated_at": now,
        "document_count": 0,
    }


@router.patch("/{project_id}", response_model=ResearchProjectResponse)
async def archive_project(project_id: str, body: ProjectArchive, request: Request) -> dict:
    if body.archived is None and body.name is None:
        raise HTTPException(status_code=422, detail="Provide a project name or archived state")
    async with await _session() as session:
        owner = await _user_id(request)
        current = await _owned_project(session, project_id, owner)
        values = {
            "archived": current["archived"] if body.archived is None else body.archived,
            "name": current["name"] if body.name is None else body.name.strip(),
            "updated": datetime.now(UTC),
            "id": project_id,
            "owner": owner,
        }
        await session.execute(
            text("UPDATE wu_research_projects SET archived=:archived, name=:name, updated_at=:updated WHERE id=:id AND owner_id=:owner"),
            values,
        )
        await session.commit()
        return await _owned_project(session, project_id, owner)


@router.delete("/{project_id}")
async def delete_project(project_id: str, request: Request) -> None:
    async with await _session() as session:
        owner = await _user_id(request)
        count = await session.scalar(text("SELECT COUNT(*) FROM wu_project_documents pd JOIN wu_research_projects p ON p.id=pd.project_id WHERE pd.project_id=:project AND p.owner_id=:owner"), {"project": project_id, "owner": owner})
        if count:
            raise HTTPException(status_code=409, detail="Cannot delete a project that contains documents")
        result = await session.execute(text("DELETE FROM wu_research_projects WHERE id=:project AND owner_id=:owner"), {"project": project_id, "owner": owner})
        if result.rowcount != 1:
            raise HTTPException(status_code=404, detail="Research project not found")
        await session.commit()


@router.get("/{project_id}/documents")
async def list_project_documents(project_id: str, request: Request) -> list[dict]:
    async with await _session() as session:
        owner = await _user_id(request)
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT d.id, d.title, d.edition, d.source_type, d.source_level, "
                        "d.source_institution, d.status, pd.added_at FROM wu_project_documents pd "
                        "JOIN wu_source_documents d ON d.id=pd.document_id "
                        "JOIN wu_research_projects p ON p.id=pd.project_id "
                        "WHERE pd.project_id=:project AND p.owner_id=:owner "
                        "ORDER BY pd.added_at DESC"
                    ),
                    {"project": project_id, "owner": owner},
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]


@router.post("/{project_id}/documents", status_code=201)
async def add_project_document(project_id: str, body: ProjectDocument, request: Request) -> dict:
    async with await _session() as session:
        owner = await _user_id(request)
        allowed = await session.scalar(text("SELECT 1 FROM wu_research_projects WHERE id=:project AND owner_id=:owner"), {"project": project_id, "owner": owner})
        if not allowed:
            raise HTTPException(status_code=404, detail="Research project not found")
        exists = await session.scalar(text("SELECT 1 FROM wu_source_documents WHERE id=:document"), {"document": body.document_id})
        if not exists:
            raise HTTPException(status_code=404, detail="Source document not found")
        now = datetime.now(UTC)
        already = await session.scalar(text("SELECT 1 FROM wu_project_documents WHERE project_id=:project AND document_id=:document"), {"project": project_id, "document": body.document_id})
        if not already:
            await session.execute(
                text("INSERT INTO wu_project_documents (project_id, document_id, added_by, added_at) VALUES (:project,:document,:owner,:added)"),
                {"project": project_id, "document": body.document_id, "owner": owner, "added": now},
            )
        await session.commit()
        return {"project_id": project_id, "document_id": body.document_id, "added_by": owner, "added_at": now}


@router.delete("/{project_id}/documents/{document_id}", status_code=204)
async def remove_project_document(project_id: str, document_id: str, request: Request) -> None:
    async with await _session() as session:
        result = await session.execute(
            text("DELETE FROM wu_project_documents WHERE project_id=:project AND document_id=:document AND project_id IN (SELECT id FROM wu_research_projects WHERE owner_id=:owner)"),
            {"project": project_id, "document": document_id, "owner": await _user_id(request)},
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=404, detail="Project document association not found")
        await session.commit()


@router.get("/{project_id}/records")
async def list_project_records(project_id: str, request: Request) -> list[dict]:
    async with await _session() as session:
        owner = await _user_id(request)
        await _owned_project(session, project_id, owner)
        rows = (
            (
                await session.execute(
                    text("SELECT id, project_id, kind, content, created_by, created_at, updated_at FROM wu_project_records WHERE project_id=:project ORDER BY created_at DESC, id DESC"),
                    {"project": project_id},
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]


@router.post("/{project_id}/records", status_code=201)
async def create_project_record(project_id: str, body: ProjectRecordCreate, request: Request) -> dict:
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Research record cannot be blank")
    record_id = f"project-record-{uuid4().hex}"
    now = datetime.now(UTC)
    async with await _session() as session:
        owner = await _user_id(request)
        await _owned_project(session, project_id, owner)
        await session.execute(
            text("INSERT INTO wu_project_records (id, project_id, kind, content, created_by, created_at, updated_at) VALUES (:id,:project,:kind,:content,:owner,:created,:updated)"),
            {
                "id": record_id,
                "project": project_id,
                "kind": body.kind.value,
                "content": content,
                "owner": owner,
                "created": now,
                "updated": now,
            },
        )
        await session.commit()
    return {
        "id": record_id,
        "project_id": project_id,
        "kind": body.kind.value,
        "content": content,
        "created_by": owner,
        "created_at": now,
        "updated_at": now,
    }


@router.patch("/{project_id}/records/{record_id}")
async def update_project_record(project_id: str, record_id: str, body: ProjectRecordUpdate, request: Request) -> dict:
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Research record cannot be blank")
    async with await _session() as session:
        owner = await _user_id(request)
        result = await session.execute(
            text("UPDATE wu_project_records SET content=:content, updated_at=:updated WHERE id=:record AND project_id=:project AND project_id IN (SELECT id FROM wu_research_projects WHERE owner_id=:owner)"),
            {
                "content": content,
                "updated": datetime.now(UTC),
                "record": record_id,
                "project": project_id,
                "owner": owner,
            },
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=404, detail="Research record not found")
        await session.commit()
        row = (
            (
                await session.execute(
                    text("SELECT id, project_id, kind, content, created_by, created_at, updated_at FROM wu_project_records WHERE id=:record"),
                    {"record": record_id},
                )
            )
            .mappings()
            .one()
        )
        return dict(row)


@router.delete("/{project_id}/records/{record_id}", status_code=204)
async def delete_project_record(project_id: str, record_id: str, request: Request) -> None:
    async with await _session() as session:
        result = await session.execute(
            text("DELETE FROM wu_project_records WHERE id=:record AND project_id=:project AND project_id IN (SELECT id FROM wu_research_projects WHERE owner_id=:owner)"),
            {"record": record_id, "project": project_id, "owner": await _user_id(request)},
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=404, detail="Research record not found")
        await session.commit()
