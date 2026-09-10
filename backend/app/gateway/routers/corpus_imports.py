from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.gateway.deps import require_business_capability
from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.wu_culture import SqlCorpusImportRepository

router = APIRouter(prefix="/api/corpus-imports", tags=["corpus-imports"])


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorpusImportBatchResponse(_Model):
    id: str
    corpus_root_id: str
    manifest_sha256: str
    status: Literal["running", "completed", "failed"]
    created_by: str
    created_at: datetime
    completed_at: datetime | None = None
    item_count: int = Field(ge=0)
    page_count: int = Field(ge=0)
    quality_issue_count: int = Field(ge=0)


class CorpusImportItemResponse(_Model):
    id: str
    batch_id: str
    bundle_id: str
    document_id: str
    source_file_id: str
    chunk_set_id: str
    page_count: int = Field(ge=0)
    quality_issue_count: int = Field(ge=0)
    status: Literal["completed", "failed"]
    imported_by: str
    imported_at: datetime
    error_code: str | None = None
    error_message: str | None = None


class CorpusQualityIssueResponse(_Model):
    id: str
    import_item_id: str
    bundle_id: str
    source_file_id: str
    code: str
    severity: Literal["warning"]
    field: str
    count: int = Field(ge=1)
    physical_page_number: int = Field(ge=1)
    folio_label: str
    message: str


def get_corpus_import_repository() -> SqlCorpusImportRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("Corpus import operations require a SQL database")
    return SqlCorpusImportRepository(session_factory)


async def _require_source_manager(request: Request) -> None:
    await require_business_capability(request, "source:manage", detail="Source management privileges are required")


@router.get("", response_model=list[CorpusImportBatchResponse])
async def list_corpus_import_batches(
    request: Request,
    repository: SqlCorpusImportRepository = Depends(get_corpus_import_repository),
):
    await _require_source_manager(request)
    return await repository.list_batches()


@router.get("/{batch_id}/items", response_model=list[CorpusImportItemResponse])
async def list_corpus_import_items(
    batch_id: str,
    request: Request,
    repository: SqlCorpusImportRepository = Depends(get_corpus_import_repository),
):
    await _require_source_manager(request)
    return await repository.list_items(batch_id)


@router.get("/items/{item_id}/quality-issues", response_model=list[CorpusQualityIssueResponse])
async def list_corpus_quality_issues(
    item_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: SqlCorpusImportRepository = Depends(get_corpus_import_repository),
):
    await _require_source_manager(request)
    return await repository.list_quality_issues(item_id, limit=limit, offset=offset)
