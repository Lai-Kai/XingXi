from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Annotated, Literal
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from wu_culture import (
    AuthorizationStatus,
    AuthorizedUse,
    CopyrightStatus,
    DocumentParseError,
    DocumentParseRequest,
    DuplicateSourceFileError,
    ParsedDocument,
    ParsedDocumentRepository,
    SourceAccessDecision,
    SourceAuthorizationEvent,
    SourceDocument,
    SourceDocumentLibraryRepository,
    SourceDocumentRepository,
    SourceDocumentStatus,
    SourceFile,
    SourceFileRepository,
    SourceLevel,
    SourceType,
    VisibilityScope,
    evaluate_source_access,
    parse_document,
)
from wu_culture.chunking import ChunkingPolicy, ChunkSet, ChunkSourcePage, StructuredChunkRepository, chunk_cleaned_pages
from wu_culture.cleaning import CleanedOcrPage, RawOcrPage, TextCleaningPolicy, TextCleaningRepository, clean_ocr_pages
from wu_culture.ingestion import (
    IngestionConcurrencyError,
    IngestionEvent,
    IngestionIdempotencyConflict,
    IngestionJob,
    IngestionJobRepository,
    IngestionStateError,
    IngestionStepName,
    begin_step,
    cancel_job,
    complete_step,
    create_ingestion_job,
    fail_step,
    retry_failed_step,
)
from wu_culture.ocr import OcrPageAttempt, OcrRepository, OcrService, OpenAICompatibleVisionOcrProvider, render_ocr_pages
from wu_culture.review import (
    PublicationGateDecision,
    ReviewBatchRequest,
    ReviewConflictError,
    ReviewQueue,
    ReviewRecord,
    ReviewRepository,
    ReviewTargetNotFound,
    ReviewTargetType,
)
from wu_culture.storage import ObjectKind, ObjectMetadataRepository, ObjectStorage, PutObjectRequest

from app.gateway.deps import require_business_capability
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/source-documents", tags=["source-documents"])
public_router = APIRouter(prefix="/api/public/source-documents", tags=["public-source-access"])
_ADMIN_REQUIRED_DETAIL = "Admin privileges are required to manage source documents"
logger = logging.getLogger(__name__)


class SourceDocumentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1)
    edition: str = Field(min_length=1)
    source_institution: str = Field(min_length=1)
    source_type: SourceType
    source_type_label: str | None = Field(default=None, min_length=1, max_length=100)
    source_level: SourceLevel
    holder: str = Field(min_length=1)
    status: SourceDocumentStatus = SourceDocumentStatus.REGISTERED

    @model_validator(mode="after")
    def validate_source_type(self) -> SourceDocumentCreateRequest:
        if self.source_type is SourceType.OTHER and not self.source_type_label:
            raise ValueError("source_type_label is required when source_type is other")
        if self.source_type is not SourceType.OTHER and self.source_type_label is not None:
            raise ValueError("source_type_label is only allowed when source_type is other")
        return self


class SourceDocumentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1)
    edition: str | None = Field(default=None, min_length=1)
    source_institution: str | None = Field(default=None, min_length=1)
    source_type: SourceType | None = None
    source_type_label: str | None = Field(default=None, min_length=1, max_length=100)
    source_level: SourceLevel | None = None
    holder: str | None = Field(default=None, min_length=1)
    status: SourceDocumentStatus | None = None

    @model_validator(mode="after")
    def require_update(self) -> SourceDocumentUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one source document field is required")
        if self.source_type is SourceType.OTHER and not self.source_type_label:
            raise ValueError("source_type_label is required when source_type is other")
        if self.source_type not in {None, SourceType.OTHER} and self.source_type_label is not None:
            raise ValueError("source_type_label is only allowed when source_type is other")
        return self


class SourceDocumentPageResponse(BaseModel):
    items: list[SourceDocument]
    total: int
    limit: int
    offset: int


class SourceDocumentLibraryFileResponse(BaseModel):
    file: SourceFile
    ingestion_job: IngestionJob | None


class SourceDocumentLibraryItemResponse(BaseModel):
    source: SourceDocument
    files: list[SourceDocumentLibraryFileResponse]


class SourceDocumentLibraryPageResponse(BaseModel):
    items: list[SourceDocumentLibraryItemResponse]
    total: int
    limit: int
    offset: int


class SourceAuthorizationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    copyright_status: CopyrightStatus
    authorization_status: AuthorizationStatus
    authorization_basis: str | None = Field(default=None, min_length=1)
    authorization_valid_from: datetime | None = None
    authorization_valid_until: datetime | None = None
    visibility_scope: VisibilityScope
    authorized_uses: tuple[AuthorizedUse, ...] = ()
    authorization_proof_object_key: str | None = Field(default=None, min_length=1)
    change_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_authorization(self) -> SourceAuthorizationUpdateRequest:
        for name in ("authorization_valid_from", "authorization_valid_until"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must include a timezone")
        if self.authorization_valid_from is not None and self.authorization_valid_until is not None and self.authorization_valid_until <= self.authorization_valid_from:
            raise ValueError("authorization_valid_until must be after authorization_valid_from")
        if self.authorization_status is AuthorizationStatus.ACTIVE:
            if not self.authorization_basis:
                raise ValueError("active authorization requires authorization_basis")
            if not self.authorized_uses:
                raise ValueError("active authorization requires at least one authorized use")
        if self.authorization_status is AuthorizationStatus.UNCONFIRMED and self.authorized_uses:
            raise ValueError("unconfirmed authorization cannot grant uses")
        return self


def get_source_document_repository() -> SourceDocumentRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Source document registration requires a SQL database")
    from deerflow.persistence.wu_culture import SqlSourceDocumentRepository

    return SqlSourceDocumentRepository(session_factory)


def get_source_document_library_repository() -> SourceDocumentLibraryRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Source document library requires a SQL database")
    from deerflow.persistence.wu_culture import SqlSourceDocumentRepository

    return SqlSourceDocumentRepository(session_factory)


def get_source_file_repository() -> SourceFileRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Source file upload requires a SQL database")
    from deerflow.persistence.wu_culture import SqlSourceFileRepository

    return SqlSourceFileRepository(session_factory)


def get_parsed_document_repository() -> ParsedDocumentRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Digital document parsing requires a SQL database")
    from deerflow.persistence.wu_culture import SqlParsedDocumentRepository

    return SqlParsedDocumentRepository(session_factory)


def get_source_object_storage() -> ObjectStorage:
    from deerflow.config.app_config import get_app_config
    from deerflow.object_storage import create_object_storage

    return create_object_storage(get_app_config().object_storage)


def get_ocr_repository() -> OcrRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="OCR requires a SQL database")
    from deerflow.persistence.wu_culture import SqlOcrRepository

    return SqlOcrRepository(session_factory)


def get_text_cleaning_repository() -> TextCleaningRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Text cleaning requires a SQL database")
    from deerflow.persistence.wu_culture import SqlTextCleaningRepository

    return SqlTextCleaningRepository(session_factory)


def get_structured_chunk_repository() -> StructuredChunkRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Structured chunking requires a SQL database")
    from deerflow.persistence.wu_culture import SqlStructuredChunkRepository

    return SqlStructuredChunkRepository(session_factory)


def get_ingestion_job_repository() -> IngestionJobRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Ingestion jobs require a SQL database")
    from deerflow.persistence.wu_culture import SqlIngestionJobRepository

    return SqlIngestionJobRepository(session_factory)


def get_review_repository() -> ReviewRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Text review requires a SQL database")
    from deerflow.persistence.wu_culture import SqlReviewRepository

    return SqlReviewRepository(session_factory)


def get_optional_ingestion_job_repository() -> IngestionJobRepository | None:
    session_factory = get_session_factory()
    if session_factory is None:
        return None
    from deerflow.persistence.wu_culture import SqlIngestionJobRepository

    return SqlIngestionJobRepository(session_factory)


def get_ingestion_max_concurrent_jobs() -> int:
    from deerflow.config.app_config import get_app_config

    return get_app_config().ingestion.max_concurrent_jobs


def get_ingestion_lease_seconds() -> int:
    from deerflow.config.app_config import get_app_config

    return get_app_config().ingestion.lease_seconds


def get_ocr_object_metadata_repository() -> ObjectMetadataRepository:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="OCR page images require a SQL database")
    from deerflow.persistence.object_storage import SqlObjectMetadataRepository

    return SqlObjectMetadataRepository(session_factory)


def get_corpus_import_config():
    from deerflow.config.app_config import get_app_config

    return get_app_config().corpus_import


def get_ocr_config():
    from deerflow.config.app_config import get_app_config

    return get_app_config().ocr


def get_ocr_service() -> OcrService:
    from deerflow.config.app_config import get_app_config

    app_config = get_app_config()
    config = app_config.ocr
    if not config.enabled or config.model_name is None:
        raise HTTPException(status_code=503, detail={"code": "ocr_disabled", "message": "OCR is not enabled"})
    model = app_config.get_model_config(config.model_name)
    if model is None or not model.supports_vision:
        raise HTTPException(status_code=503, detail={"code": "ocr_model_invalid", "message": "OCR vision model is not configured"})
    api_key = getattr(model, "api_key", None) or getattr(model, "openai_api_key", None)
    if hasattr(api_key, "get_secret_value"):
        api_key = api_key.get_secret_value()
    if not api_key:
        raise HTTPException(status_code=503, detail={"code": "ocr_api_key_missing", "message": "OCR model API key is missing"})
    base_url = getattr(model, "base_url", None) or getattr(model, "openai_api_base", None) or getattr(model, "api_base", None) or "https://api.openai.com/v1"
    provider = OpenAICompatibleVisionOcrProvider(
        base_url=str(base_url),
        api_key=str(api_key),
        model=model.model,
        api_mode=config.api_mode,
        timeout_seconds=config.timeout,
    )
    return OcrService(
        provider,
        languages=config.languages,
        review_confidence_threshold=config.review_confidence_threshold,
        max_concurrency=config.max_concurrency,
    )


class SourceFileUploadItem(BaseModel):
    filename: str
    status: str
    file: SourceFile | None = None
    existing_file: SourceFile | None = None
    error_code: str | None = None
    error: str | None = None
    ingestion_job: IngestionJob | None = None
    ingestion_error: str | None = None


class SourceFileUploadResponse(BaseModel):
    success_count: int
    failure_count: int
    items: list[SourceFileUploadItem]


class SourceFileParseResponse(BaseModel):
    document: ParsedDocument
    reused_existing: bool


class SourceFileOcrResponse(BaseModel):
    source_file_id: str
    reused_existing: bool
    attempts: tuple[OcrPageAttempt, ...]


class SourceFileCleaningResponse(BaseModel):
    source_file_id: str
    pages: tuple[CleanedOcrPage, ...]


class SourceFileChunkingResponse(BaseModel):
    reused_existing: bool
    chunk_set: ChunkSet


class IngestionJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=1, max_length=255)


class IngestionJobCreateResponse(BaseModel):
    reused_existing: bool
    job: IngestionJob


class IngestionStepStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    worker_id: str = Field(min_length=1, max_length=255)


class IngestionStepCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    output_ref: str | None = Field(default=None, min_length=1)


class IngestionStepFailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    error_code: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    error_message: str = Field(min_length=1, max_length=4000)
    retryable: bool = True


class ReviewFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chunk_set_id: str = Field(min_length=1, max_length=255)
    ingestion_job_id: str = Field(min_length=1, max_length=255)


class SourceUploadLimits(BaseModel):
    max_files: int = Field(ge=1)
    max_file_size: int = Field(ge=1)
    max_total_size: int = Field(ge=1)


class SourceUploadLimitsResponse(SourceUploadLimits):
    allowed_extensions: tuple[str, ...]


class _SourceUploadRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_SOURCE_UPLOAD_CHUNK_SIZE = 64 * 1024
_DEFAULT_MAX_FILES = 10
_DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024
_DEFAULT_MAX_TOTAL_SIZE = 100 * 1024 * 1024


async def _create_upload_ingestion_job(
    source_file: SourceFile,
    *,
    admin_id: str,
    repository: IngestionJobRepository | None,
) -> tuple[IngestionJob | None, str | None]:
    if repository is None:
        return None, "Ingestion persistence is unavailable"
    now = datetime.now(UTC)
    job, event = create_ingestion_job(
        job_id=f"ingestion-job-{uuid4().hex}",
        document_id=source_file.document_id,
        source_file_id=source_file.id,
        idempotency_key=f"source-file:{source_file.id}",
        created_by=admin_id,
        now=now,
    )
    try:
        stored, _ = await repository.create(job, event)
        return stored, None
    except Exception as exc:
        logger.exception("Failed to create ingestion job for source file %s", source_file.id)
        return None, str(exc)


@router.get("/ocr/review-queue", response_model=list[OcrPageAttempt])
async def list_ocr_review_queue(
    request: Request,
    repository: OcrRepository = Depends(get_ocr_repository),
) -> list[OcrPageAttempt]:
    await _admin_id(request)
    return await repository.list_review_queue()


def _configured_upload_limit(name: str, default: int) -> int:
    from deerflow.config.app_config import get_app_config

    uploads = getattr(get_app_config(), "uploads", None)
    value = uploads.get(name, default) if isinstance(uploads, dict) else getattr(uploads, name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def get_source_upload_limits() -> SourceUploadLimits:
    return SourceUploadLimits(
        max_files=_configured_upload_limit("max_files", _DEFAULT_MAX_FILES),
        max_file_size=_configured_upload_limit("max_file_size", _DEFAULT_MAX_FILE_SIZE),
        max_total_size=_configured_upload_limit("max_total_size", _DEFAULT_MAX_TOTAL_SIZE),
    )


def get_source_upload_staging_dir() -> Path:
    from deerflow.config.runtime_paths import runtime_home

    return runtime_home() / "source-upload-staging"


@router.get("/upload/limits", response_model=SourceUploadLimitsResponse)
async def get_source_upload_limits_endpoint(
    request: Request,
    limits: SourceUploadLimits = Depends(get_source_upload_limits),
) -> SourceUploadLimitsResponse:
    await _admin_id(request)
    return SourceUploadLimitsResponse(
        **limits.model_dump(),
        allowed_extensions=(".pdf", ".png", ".jpg", ".jpeg", ".docx", ".txt", ".md", ".markdown"),
    )


def _create_staging_file(staging_dir: Path) -> tuple[Path, object]:
    staging_dir.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix="source-upload-", suffix=".tmp", dir=staging_dir)
    return Path(raw_path), os.fdopen(descriptor, "wb")


async def _stream_upload_to_staging(
    upload: UploadFile,
    *,
    staging_dir: Path,
    limits: SourceUploadLimits,
    total_size: int,
) -> tuple[Path, int]:
    path, handle = await asyncio.to_thread(_create_staging_file, staging_dir)
    file_size = 0
    try:
        while chunk := await upload.read(_SOURCE_UPLOAD_CHUNK_SIZE):
            file_size += len(chunk)
            if file_size > limits.max_file_size:
                raise _SourceUploadRejected("file_too_large", f"File exceeds {limits.max_file_size} bytes")
            if total_size + file_size > limits.max_total_size:
                raise _SourceUploadRejected("batch_too_large", f"Batch exceeds {limits.max_total_size} bytes")
            await asyncio.to_thread(handle.write, chunk)
        if file_size == 0:
            raise _SourceUploadRejected("empty_file", "Empty files are not allowed")
        await asyncio.to_thread(handle.flush)
        return path, file_size
    except BaseException:
        await asyncio.to_thread(handle.close)
        await asyncio.to_thread(path.unlink, missing_ok=True)
        raise
    finally:
        if not handle.closed:
            await asyncio.to_thread(handle.close)


def _detect_source_file_mime(filename: str, path: Path) -> str | None:
    suffix = PurePath(filename).suffix.lower()
    with path.open("rb") as source:
        prefix = source.read(1024)
    if suffix == ".pdf" and b"%PDF-" in prefix:
        return "application/pdf"
    if suffix == ".png" and prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if suffix in {".jpg", ".jpeg"} and prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if suffix == ".docx":
        try:
            with ZipFile(path) as archive:
                names = set(archive.namelist())
        except BadZipFile:
            return None
        if "[Content_Types].xml" in names and "word/document.xml" in names:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".txt" and b"\x00" not in prefix:
        return "text/plain"
    if suffix in {".md", ".markdown"} and b"\x00" not in prefix:
        return "text/markdown"
    return None


async def _admin_id(request: Request) -> str:
    user = await require_business_capability(request, "source:manage", detail=_ADMIN_REQUIRED_DETAIL)
    return str(user.id)


@router.post("", response_model=SourceDocument, status_code=status.HTTP_201_CREATED)
async def create_source_document(
    body: SourceDocumentCreateRequest,
    request: Request,
    repository: SourceDocumentRepository = Depends(get_source_document_repository),
) -> SourceDocument:
    admin_id = await _admin_id(request)
    now = datetime.now(UTC)
    document = SourceDocument(
        id=f"source-{uuid4().hex}",
        title=body.title,
        edition=body.edition,
        source_institution=body.source_institution,
        source_type=body.source_type,
        source_type_label=body.source_type_label,
        source_level=body.source_level,
        holder=body.holder,
        status=body.status,
        copyright_status=CopyrightStatus.UNKNOWN,
        created_by=admin_id,
        created_at=now,
        updated_by=admin_id,
        updated_at=now,
    )
    return await repository.create(document)


@router.get("", response_model=list[SourceDocument])
async def list_source_documents(
    request: Request,
    repository: SourceDocumentRepository = Depends(get_source_document_repository),
) -> list[SourceDocument]:
    await _admin_id(request)
    return list(await repository.list())


@router.get("/page", response_model=SourceDocumentPageResponse)
async def page_source_documents(
    request: Request,
    query: str | None = None,
    status_filter: SourceDocumentStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    repository: SourceDocumentRepository = Depends(get_source_document_repository),
) -> SourceDocumentPageResponse:
    await _admin_id(request)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    if hasattr(repository, "list_page"):
        items, total = await repository.list_page(query=query, status=status_filter, limit=limit, offset=offset)
    else:
        all_items = list(await repository.list())
        needle = query.strip().lower() if query else ""
        filtered = [item for item in all_items if (not needle or needle in item.title.lower() or needle in item.edition.lower() or needle in item.source_institution.lower()) and (status_filter is None or item.status == status_filter)]
        total = len(filtered)
        items = filtered[offset : offset + limit]
    return SourceDocumentPageResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/library/page", response_model=SourceDocumentLibraryPageResponse)
async def page_source_document_library(
    request: Request,
    query: str | None = None,
    status_filter: SourceDocumentStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    repository: SourceDocumentLibraryRepository = Depends(get_source_document_library_repository),
) -> SourceDocumentLibraryPageResponse:
    await _admin_id(request)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    items, total = await repository.list_library_page(
        query=query,
        status=status_filter.value if status_filter is not None else None,
        limit=limit,
        offset=offset,
    )
    return SourceDocumentLibraryPageResponse(
        items=[
            SourceDocumentLibraryItemResponse(
                source=item.document,
                files=[
                    SourceDocumentLibraryFileResponse(
                        file=library_file.file,
                        ingestion_job=library_file.ingestion_job,
                    )
                    for library_file in item.files
                ],
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=SourceDocument)
async def get_source_document(
    document_id: str,
    request: Request,
    repository: SourceDocumentRepository = Depends(get_source_document_repository),
) -> SourceDocument:
    await _admin_id(request)
    document = await repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return document


@router.patch("/{document_id}", response_model=SourceDocument)
async def update_source_document(
    document_id: str,
    body: SourceDocumentUpdateRequest,
    request: Request,
    repository: SourceDocumentRepository = Depends(get_source_document_repository),
) -> SourceDocument:
    admin_id = await _admin_id(request)
    existing = await repository.get(document_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    updates = body.model_dump(exclude_unset=True)
    if "source_type" in updates and updates["source_type"] is not SourceType.OTHER:
        updates.setdefault("source_type_label", None)
    updates.update(updated_by=admin_id, updated_at=datetime.now(UTC))
    try:
        updated_document = SourceDocument.model_validate({**existing.model_dump(), **updates})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid source type and custom label combination") from exc
    updated = await repository.update(updated_document)
    if updated is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return updated


@router.put("/{document_id}/authorization", response_model=SourceDocument)
async def update_source_authorization(
    document_id: str,
    body: SourceAuthorizationUpdateRequest,
    request: Request,
    repository: SourceDocumentRepository = Depends(get_source_document_repository),
) -> SourceDocument:
    admin_id = await _admin_id(request)
    existing = await repository.get(document_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    changed_at = datetime.now(UTC)
    updates = body.model_dump(exclude={"change_reason"})
    updates.update(updated_by=admin_id, updated_at=changed_at)
    next_document = existing.model_copy(update=updates)
    event = SourceAuthorizationEvent(
        id=f"authorization-event-{uuid4().hex}",
        document_id=document_id,
        previous_status=existing.authorization_status,
        new_status=next_document.authorization_status,
        previous_copyright_status=existing.copyright_status,
        new_copyright_status=next_document.copyright_status,
        new_visibility_scope=next_document.visibility_scope,
        new_authorized_uses=next_document.authorized_uses,
        authorization_valid_until=next_document.authorization_valid_until,
        authorization_proof_object_key=next_document.authorization_proof_object_key,
        changed_by=admin_id,
        changed_at=changed_at,
        reason=body.change_reason,
    )
    updated = await repository.update_authorization(next_document, event)
    if updated is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return updated


@router.get("/{document_id}/authorization/history", response_model=list[SourceAuthorizationEvent])
async def list_source_authorization_history(
    document_id: str,
    request: Request,
    repository: SourceDocumentRepository = Depends(get_source_document_repository),
) -> list[SourceAuthorizationEvent]:
    await _admin_id(request)
    if await repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return list(await repository.list_authorization_events(document_id))


@router.post("/{document_id}/files", response_model=SourceFileUploadResponse)
async def upload_source_files(
    document_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    duplicate_policy: Annotated[Literal["report", "reference_existing", "new_version"], Form()] = "report",
    version_of_file_id: Annotated[str | None, Form()] = None,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    object_storage: ObjectStorage = Depends(get_source_object_storage),
    limits: SourceUploadLimits = Depends(get_source_upload_limits),
    staging_dir: Path = Depends(get_source_upload_staging_dir),
    ingestion_repository: IngestionJobRepository | None = Depends(get_optional_ingestion_job_repository),
) -> SourceFileUploadResponse:
    admin_id = await _admin_id(request)
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    version_target = await file_repository.get(version_of_file_id) if version_of_file_id else None

    items: list[SourceFileUploadItem] = []
    total_size = 0
    for index, upload in enumerate(files):
        filename = upload.filename or "unnamed"
        staging_path: Path | None = None
        metadata = None
        object_was_new = False
        try:
            if duplicate_policy == "new_version" and version_target is None:
                code = "version_target_required" if version_of_file_id is None else "version_target_not_found"
                raise _SourceUploadRejected(code, "A valid version_of_file_id is required")
            if index >= limits.max_files:
                raise _SourceUploadRejected("too_many_files", f"Batch accepts at most {limits.max_files} files")
            staging_path, file_size = await _stream_upload_to_staging(
                upload,
                staging_dir=staging_dir,
                limits=limits,
                total_size=total_size,
            )
            total_size += file_size
            mime_type = await asyncio.to_thread(_detect_source_file_mime, filename, staging_path)
            if mime_type is None:
                raise _SourceUploadRejected("invalid_file_type", "Unsupported or invalid file type")
            content = await asyncio.to_thread(staging_path.read_bytes)
            digest = hashlib.sha256(content).hexdigest()
            existing_file = await file_repository.find_by_sha256(digest)
            if existing_file is not None:
                if duplicate_policy in {"reference_existing", "new_version"}:
                    existing_owner = existing_file.object_key.split("/", 2)[1]
                    existing_metadata = await object_storage.stat(
                        owner_id=existing_owner,
                        object_key=existing_file.object_key,
                    )
                    source_file = SourceFile(
                        id=f"source-file-{uuid4().hex}",
                        document_id=document_id,
                        object_key=existing_file.object_key,
                        original_filename=filename,
                        mime_type=existing_metadata.mime_type,
                        size=existing_metadata.size,
                        sha256=digest,
                        duplicate_of_file_id=existing_file.id,
                        version_of_file_id=version_target.id if duplicate_policy == "new_version" and version_target else None,
                        uploaded_by=admin_id,
                        uploaded_at=datetime.now(UTC),
                    )
                    await file_repository.attach(source_file, existing_metadata)
                    ingestion_job, ingestion_error = await _create_upload_ingestion_job(
                        source_file,
                        admin_id=admin_id,
                        repository=ingestion_repository,
                    )
                    items.append(
                        SourceFileUploadItem(
                            filename=filename,
                            status="uploaded",
                            file=source_file,
                            ingestion_job=ingestion_job,
                            ingestion_error=ingestion_error,
                        )
                    )
                    continue
                items.append(
                    SourceFileUploadItem(
                        filename=filename,
                        status="failed",
                        existing_file=existing_file,
                        error_code="duplicate_file",
                        error="File content already exists",
                    )
                )
                continue
            if duplicate_policy == "reference_existing":
                raise _SourceUploadRejected(
                    "reference_target_not_found",
                    "Reference existing requires identical file content",
                )
            same_name_file = await file_repository.find_by_document_and_filename(document_id, filename)
            if same_name_file is not None and duplicate_policy == "report":
                items.append(
                    SourceFileUploadItem(
                        filename=filename,
                        status="failed",
                        existing_file=same_name_file,
                        error_code="same_name_different_content",
                        error="A different file already uses this filename",
                    )
                )
                continue
            expected_key = f"users/{document_id}/objects/{ObjectKind.ORIGINAL.value}/{digest[:2]}/{digest}"
            try:
                await object_storage.stat(owner_id=document_id, object_key=expected_key)
            except FileNotFoundError:
                object_was_new = True
            metadata = await object_storage.put(
                PutObjectRequest(
                    owner_id=document_id,
                    kind=ObjectKind.ORIGINAL,
                    content=content,
                    mime_type=mime_type,
                    original_filename=filename,
                )
            )
            source_file = SourceFile(
                id=f"source-file-{uuid4().hex}",
                document_id=document_id,
                object_key=metadata.object_key,
                original_filename=filename,
                mime_type=metadata.mime_type,
                size=metadata.size,
                sha256=digest,
                version_of_file_id=version_target.id if duplicate_policy == "new_version" and version_target else None,
                uploaded_by=admin_id,
                uploaded_at=datetime.now(UTC),
            )
            await file_repository.attach(source_file, metadata)
            ingestion_job, ingestion_error = await _create_upload_ingestion_job(
                source_file,
                admin_id=admin_id,
                repository=ingestion_repository,
            )
            items.append(
                SourceFileUploadItem(
                    filename=filename,
                    status="uploaded",
                    file=source_file,
                    ingestion_job=ingestion_job,
                    ingestion_error=ingestion_error,
                )
            )
        except _SourceUploadRejected as exc:
            items.append(SourceFileUploadItem(filename=filename, status="failed", error_code=exc.code, error=exc.message))
        except DuplicateSourceFileError as exc:
            logger.info("Concurrent duplicate source upload detected for %s", filename)
            if metadata is not None and object_was_new:
                try:
                    await object_storage.delete(
                        owner_id=document_id,
                        object_key=metadata.object_key,
                        reason="concurrent duplicate source upload",
                    )
                except Exception:
                    logger.exception("Failed to remove object after concurrent duplicate detection: %s", metadata.object_key)
            items.append(
                SourceFileUploadItem(
                    filename=filename,
                    status="failed",
                    existing_file=exc.existing_file,
                    error_code="duplicate_file",
                    error="File content already exists",
                )
            )
        except Exception:
            logger.exception("Source file upload failed for document %s and file %s", document_id, filename)
            if metadata is not None and object_was_new:
                try:
                    await object_storage.delete(
                        owner_id=document_id,
                        object_key=metadata.object_key,
                        reason="source file database binding failed",
                    )
                except Exception:
                    logger.exception("Failed to remove object after source file binding failure: %s", metadata.object_key)
            items.append(
                SourceFileUploadItem(
                    filename=filename,
                    status="failed",
                    error_code="storage_failed",
                    error="File storage failed; retry this file",
                )
            )
        finally:
            await upload.close()
            if staging_path is not None:
                await asyncio.to_thread(staging_path.unlink, missing_ok=True)

    success_count = sum(item.status == "uploaded" for item in items)
    return SourceFileUploadResponse(success_count=success_count, failure_count=len(items) - success_count, items=items)


@router.get("/{document_id}/files", response_model=list[SourceFile])
async def list_source_files(
    document_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
) -> list[SourceFile]:
    await _admin_id(request)
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return list(await file_repository.list_for_document(document_id))


async def _canonical_source_file(source_file: SourceFile, repository: SourceFileRepository) -> SourceFile:
    if source_file.duplicate_of_file_id is None:
        return source_file
    canonical = await repository.get(source_file.duplicate_of_file_id)
    if canonical is None:
        raise HTTPException(status_code=409, detail={"code": "canonical_file_missing", "message": "Canonical source file is missing"})
    return canonical


@router.get("/{document_id}/files/{file_id}/content")
async def get_source_file_content(
    document_id: str,
    file_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    metadata_repository: ObjectMetadataRepository = Depends(get_ocr_object_metadata_repository),
    object_storage: ObjectStorage = Depends(get_source_object_storage),
    corpus_config=Depends(get_corpus_import_config),
):
    await _admin_id(request)
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    source_file = await file_repository.get(file_id)
    if source_file is None or source_file.document_id != document_id:
        raise HTTPException(status_code=404, detail="Source file not found")
    canonical = await _canonical_source_file(source_file, file_repository)
    metadata = await metadata_repository.get(owner_id=canonical.document_id, object_key=canonical.object_key)
    if metadata is None:
        raise HTTPException(status_code=409, detail={"code": "object_metadata_missing", "message": "Source object metadata is missing"})
    if metadata.backend == "mounted":
        try:
            path = corpus_config.resolve_storage_uri(metadata.storage_uri)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "mounted_source_invalid", "message": str(exc)}) from exc
        if path.is_symlink() or not path.is_file() or path.stat().st_size != metadata.size:
            raise HTTPException(
                status_code=409,
                detail={"code": "mounted_source_changed", "message": "Mounted source no longer matches its registered size"},
            )
        return FileResponse(path, media_type=metadata.mime_type, filename=metadata.original_filename)
    stored = await object_storage.get(owner_id=canonical.document_id, object_key=canonical.object_key)
    return Response(
        content=stored.content,
        media_type=stored.metadata.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{canonical.original_filename}"'},
    )


@router.post("/{document_id}/files/{file_id}/parse", response_model=SourceFileParseResponse)
async def parse_source_file(
    document_id: str,
    file_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    parsed_repository: ParsedDocumentRepository = Depends(get_parsed_document_repository),
    object_storage: ObjectStorage = Depends(get_source_object_storage),
) -> SourceFileParseResponse:
    await _admin_id(request)
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    source_file = await file_repository.get(file_id)
    if source_file is None or source_file.document_id != document_id:
        raise HTTPException(status_code=404, detail="Source file not found")
    canonical = await _canonical_source_file(source_file, file_repository)
    existing = await parsed_repository.get_by_source_file_id(canonical.id)
    if existing is not None:
        return SourceFileParseResponse(document=existing, reused_existing=True)

    owner_id = canonical.object_key.split("/", 2)[1]
    stored = await object_storage.get(owner_id=owner_id, object_key=canonical.object_key)
    try:
        content = await asyncio.to_thread(
            parse_document,
            DocumentParseRequest(
                filename=canonical.original_filename,
                mime_type=canonical.mime_type,
                content=stored.content,
            ),
        )
    except DocumentParseError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    parsed = ParsedDocument(
        id=f"parsed-{canonical.id}",
        source_file_id=canonical.id,
        mime_type=canonical.mime_type,
        parsed_at=datetime.now(UTC),
        **content.model_dump(),
    )
    try:
        await parsed_repository.save(parsed)
    except Exception:
        concurrent = await parsed_repository.get_by_source_file_id(canonical.id)
        if concurrent is None:
            raise
        return SourceFileParseResponse(document=concurrent, reused_existing=True)
    return SourceFileParseResponse(document=parsed, reused_existing=False)


@router.get("/{document_id}/files/{file_id}/parse", response_model=ParsedDocument)
async def get_source_file_parse(
    document_id: str,
    file_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    parsed_repository: ParsedDocumentRepository = Depends(get_parsed_document_repository),
) -> ParsedDocument:
    await _admin_id(request)
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    source_file = await file_repository.get(file_id)
    if source_file is None or source_file.document_id != document_id:
        raise HTTPException(status_code=404, detail="Source file not found")
    canonical = await _canonical_source_file(source_file, file_repository)
    parsed = await parsed_repository.get_by_source_file_id(canonical.id)
    if parsed is None:
        raise HTTPException(status_code=404, detail="Parsed document not found")
    return parsed


async def _resolve_ocr_source_file(
    *,
    document_id: str,
    file_id: str,
    document_repository: SourceDocumentRepository,
    file_repository: SourceFileRepository,
) -> SourceFile:
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    source_file = await file_repository.get(file_id)
    if source_file is None or source_file.document_id != document_id:
        raise HTTPException(status_code=404, detail="Source file not found")
    return await _canonical_source_file(source_file, file_repository)


@router.post("/{document_id}/files/{file_id}/ocr", response_model=SourceFileOcrResponse)
async def ocr_source_file(
    document_id: str,
    file_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    ocr_repository: OcrRepository = Depends(get_ocr_repository),
    object_storage: ObjectStorage = Depends(get_source_object_storage),
    metadata_repository: ObjectMetadataRepository = Depends(get_ocr_object_metadata_repository),
    ocr_service: OcrService = Depends(get_ocr_service),
    ocr_config=Depends(get_ocr_config),
) -> SourceFileOcrResponse:
    await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    existing = await ocr_repository.list_latest(canonical.id)
    if existing:
        return SourceFileOcrResponse(source_file_id=canonical.id, reused_existing=True, attempts=tuple(existing))

    owner_id = canonical.object_key.split("/", 2)[1]
    stored = await object_storage.get(owner_id=owner_id, object_key=canonical.object_key)
    try:
        pages = await asyncio.to_thread(
            render_ocr_pages,
            filename=canonical.original_filename,
            mime_type=canonical.mime_type,
            content=stored.content,
            dpi=ocr_config.render_dpi,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_ocr_source", "message": "Source file cannot be rendered for OCR"}) from exc
    if len(pages) > ocr_config.max_pages_per_batch:
        raise HTTPException(
            status_code=422,
            detail={"code": "ocr_batch_too_large", "message": f"OCR batch accepts at most {ocr_config.max_pages_per_batch} pages"},
        )

    stored_pages = []
    for page in pages:
        metadata = await object_storage.put(
            PutObjectRequest(
                owner_id=canonical.document_id,
                kind=ObjectKind.PAGE_IMAGE,
                content=page.content,
                mime_type="image/png",
                original_filename=f"{canonical.id}-page-{page.page_number}.png",
            )
        )
        await metadata_repository.save(metadata)
        stored_pages.append(page.model_copy(update={"object_key": metadata.object_key}))

    attempts = await ocr_service.recognize_pages(source_file_id=canonical.id, pages=tuple(stored_pages))
    try:
        await ocr_repository.save_attempts(attempts)
    except Exception:
        concurrent = await ocr_repository.list_latest(canonical.id)
        if not concurrent:
            raise
        return SourceFileOcrResponse(source_file_id=canonical.id, reused_existing=True, attempts=tuple(concurrent))
    return SourceFileOcrResponse(source_file_id=canonical.id, reused_existing=False, attempts=attempts)


@router.get("/{document_id}/files/{file_id}/ocr", response_model=SourceFileOcrResponse)
async def get_source_file_ocr(
    document_id: str,
    file_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    ocr_repository: OcrRepository = Depends(get_ocr_repository),
) -> SourceFileOcrResponse:
    await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    attempts = await ocr_repository.list_latest(canonical.id)
    if not attempts:
        raise HTTPException(status_code=404, detail="OCR result not found")
    return SourceFileOcrResponse(source_file_id=canonical.id, reused_existing=True, attempts=tuple(attempts))


@router.post("/{document_id}/files/{file_id}/ocr/pages/{page_number}/retry", response_model=OcrPageAttempt)
async def retry_source_file_ocr_page(
    document_id: str,
    file_id: str,
    page_number: int,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    ocr_repository: OcrRepository = Depends(get_ocr_repository),
    object_storage: ObjectStorage = Depends(get_source_object_storage),
    ocr_service: OcrService = Depends(get_ocr_service),
) -> OcrPageAttempt:
    await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    latest = next((attempt for attempt in await ocr_repository.list_latest(canonical.id) if attempt.page_number == page_number), None)
    if latest is None:
        raise HTTPException(status_code=404, detail="OCR page result not found")
    if latest.status.value != "failed":
        raise HTTPException(
            status_code=409,
            detail={"code": "ocr_page_not_failed", "message": "Only a failed OCR page can be retried"},
        )
    if latest.page_image_object_key is None:
        raise HTTPException(status_code=409, detail={"code": "ocr_page_image_missing", "message": "OCR page image is missing"})
    stored = await object_storage.get(owner_id=canonical.document_id, object_key=latest.page_image_object_key)
    from wu_culture.ocr import OcrPageImage

    page = OcrPageImage(
        page_number=latest.page_number,
        content=stored.content,
        width=latest.image_width,
        height=latest.image_height,
        sha256=latest.image_sha256,
        object_key=latest.page_image_object_key,
    )
    (attempt,) = await ocr_service.recognize_pages(
        source_file_id=canonical.id,
        pages=(page,),
        attempt_numbers={page_number: latest.attempt_number + 1},
    )
    await ocr_repository.save_attempts((attempt,))
    return attempt


@router.post("/{document_id}/files/{file_id}/clean", response_model=SourceFileCleaningResponse)
async def clean_source_file_ocr_text(
    document_id: str,
    file_id: str,
    policy: TextCleaningPolicy,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    ocr_repository: OcrRepository = Depends(get_ocr_repository),
    cleaning_repository: TextCleaningRepository = Depends(get_text_cleaning_repository),
) -> SourceFileCleaningResponse:
    admin_id = await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    attempts = [attempt for attempt in await ocr_repository.list_latest(canonical.id) if attempt.raw_text]
    if not attempts:
        raise HTTPException(
            status_code=409,
            detail={"code": "ocr_text_unavailable", "message": "No OCR page text is available for cleaning"},
        )
    previous = {page.page_number: page for page in await cleaning_repository.list_latest(canonical.id)}
    contents = clean_ocr_pages(
        tuple(
            RawOcrPage(
                source_file_id=canonical.id,
                ocr_attempt_id=attempt.id,
                page_number=attempt.page_number,
                raw_text=attempt.raw_text,
            )
            for attempt in attempts
        ),
        policy=policy,
    )
    generated_at = datetime.now(UTC)
    pages = tuple(
        CleanedOcrPage(
            id=f"cleaned-{uuid4().hex}",
            generation_number=previous.get(content.page_number).generation_number + 1 if content.page_number in previous else 1,
            policy=policy,
            generated_by=admin_id,
            generated_at=generated_at,
            **content.model_dump(),
        )
        for content in contents
    )
    try:
        await cleaning_repository.save_many(pages)
    except Exception:
        concurrent = await cleaning_repository.list_latest(canonical.id)
        expected = {page.page_number: page.generation_number for page in pages}
        if not concurrent or any(page.generation_number < expected.get(page.page_number, 0) for page in concurrent):
            raise
        return SourceFileCleaningResponse(source_file_id=canonical.id, pages=tuple(concurrent))
    return SourceFileCleaningResponse(source_file_id=canonical.id, pages=pages)


@router.get("/{document_id}/files/{file_id}/clean", response_model=SourceFileCleaningResponse)
async def get_source_file_clean_text(
    document_id: str,
    file_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    cleaning_repository: TextCleaningRepository = Depends(get_text_cleaning_repository),
) -> SourceFileCleaningResponse:
    await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    pages = await cleaning_repository.list_latest(canonical.id)
    if not pages:
        raise HTTPException(status_code=404, detail="Cleaned OCR text not found")
    return SourceFileCleaningResponse(source_file_id=canonical.id, pages=tuple(pages))


@router.get("/{document_id}/files/{file_id}/clean/pages/{page_number}/generations", response_model=list[CleanedOcrPage])
async def list_source_file_clean_generations(
    document_id: str,
    file_id: str,
    page_number: int,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    cleaning_repository: TextCleaningRepository = Depends(get_text_cleaning_repository),
) -> list[CleanedOcrPage]:
    await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    pages = await cleaning_repository.list_page_generations(canonical.id, page_number)
    if not pages:
        raise HTTPException(status_code=404, detail="Cleaned OCR page history not found")
    return pages


@router.post("/{document_id}/files/{file_id}/chunks", response_model=SourceFileChunkingResponse)
async def create_source_file_chunks(
    document_id: str,
    file_id: str,
    policy: ChunkingPolicy,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    cleaning_repository: TextCleaningRepository = Depends(get_text_cleaning_repository),
    chunk_repository: StructuredChunkRepository = Depends(get_structured_chunk_repository),
) -> SourceFileChunkingResponse:
    admin_id = await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    cleaned_pages = await cleaning_repository.list_latest(canonical.id)
    if not cleaned_pages:
        raise HTTPException(
            status_code=409,
            detail={"code": "clean_text_unavailable", "message": "No cleaned page text is available for chunking"},
        )
    input_identity = "\x1f".join(f"{page.id}:{page.raw_sha256}:{page.clean_sha256}" for page in sorted(cleaned_pages, key=lambda value: value.page_number))
    input_sha256 = hashlib.sha256(input_identity.encode("utf-8")).hexdigest()
    existing = await chunk_repository.get(canonical.id, policy.split_version)
    if existing is not None:
        if existing.policy == policy and existing.input_sha256 == input_sha256:
            return SourceFileChunkingResponse(reused_existing=True, chunk_set=existing)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "split_version_conflict",
                "message": "This split_version already refers to different policy or clean input; use a new version",
            },
        )
    result = chunk_cleaned_pages(
        document_id=canonical.document_id,
        source_file_id=canonical.id,
        pages=tuple(
            ChunkSourcePage(
                cleaned_page_id=page.id,
                page_number=page.page_number,
                raw_text=page.raw_text,
                clean_text=page.clean_text,
            )
            for page in cleaned_pages
        ),
        policy=policy,
    )
    if not result.chunks:
        raise HTTPException(status_code=422, detail={"code": "no_chunkable_text", "message": "Cleaned pages contain no paragraph text"})
    chunk_set = ChunkSet(
        id=f"chunk-set-{hashlib.sha256(f'{canonical.id}:{policy.split_version}'.encode()).hexdigest()}",
        input_sha256=input_sha256,
        generated_by=admin_id,
        generated_at=datetime.now(UTC),
        **result.model_dump(),
    )
    try:
        await chunk_repository.save(chunk_set)
    except Exception:
        concurrent = await chunk_repository.get(canonical.id, policy.split_version)
        if concurrent is None:
            raise
        if concurrent.policy != policy or concurrent.input_sha256 != input_sha256:
            raise HTTPException(status_code=409, detail={"code": "split_version_conflict", "message": "Concurrent request used this split_version for different input"})
        return SourceFileChunkingResponse(reused_existing=True, chunk_set=concurrent)
    return SourceFileChunkingResponse(reused_existing=False, chunk_set=chunk_set)


@router.get("/{document_id}/files/{file_id}/chunks", response_model=list[ChunkSet])
async def list_source_file_chunk_versions(
    document_id: str,
    file_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    chunk_repository: StructuredChunkRepository = Depends(get_structured_chunk_repository),
) -> list[ChunkSet]:
    await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    return await chunk_repository.list_versions(canonical.id)


@router.get("/{document_id}/files/{file_id}/chunks/{split_version}", response_model=ChunkSet)
async def get_source_file_chunk_version(
    document_id: str,
    file_id: str,
    split_version: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    chunk_repository: StructuredChunkRepository = Depends(get_structured_chunk_repository),
) -> ChunkSet:
    await _admin_id(request)
    canonical = await _resolve_ocr_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    chunk_set = await chunk_repository.get(canonical.id, split_version)
    if chunk_set is None:
        raise HTTPException(status_code=404, detail="Chunk version not found")
    return chunk_set


async def _resolve_ingestion_source_file(
    *,
    document_id: str,
    file_id: str,
    document_repository: SourceDocumentRepository,
    file_repository: SourceFileRepository,
) -> SourceFile:
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    source_file = await file_repository.get(file_id)
    if source_file is None or source_file.document_id != document_id:
        raise HTTPException(status_code=404, detail="Source file not found")
    return source_file


async def _resolve_ingestion_job(
    *,
    document_id: str,
    file_id: str,
    job_id: str,
    repository: IngestionJobRepository,
) -> IngestionJob:
    job = await repository.get(job_id)
    if job is None or job.document_id != document_id or job.source_file_id != file_id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


def _ingestion_transition_conflict(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "invalid_ingestion_transition", "message": str(exc)},
    )


@router.post(
    "/{document_id}/files/{file_id}/ingestion-jobs",
    response_model=IngestionJobCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_file_ingestion_job(
    document_id: str,
    file_id: str,
    body: IngestionJobCreateRequest,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJobCreateResponse:
    admin_id = await _admin_id(request)
    await _resolve_ingestion_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    job, event = create_ingestion_job(
        job_id=f"ingestion-job-{uuid4().hex}",
        document_id=document_id,
        source_file_id=file_id,
        idempotency_key=body.idempotency_key,
        created_by=admin_id,
        now=datetime.now(UTC),
    )
    try:
        stored, created = await ingestion_repository.create(job, event)
    except IngestionIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "idempotency_conflict", "message": str(exc)}) from exc
    return IngestionJobCreateResponse(reused_existing=not created, job=stored)


@router.get("/{document_id}/files/{file_id}/ingestion-jobs", response_model=list[IngestionJob])
async def list_source_file_ingestion_jobs(
    document_id: str,
    file_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> list[IngestionJob]:
    await _admin_id(request)
    await _resolve_ingestion_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    return await ingestion_repository.list_for_source_file(file_id)


@router.get("/{document_id}/files/{file_id}/ingestion-jobs/{job_id}", response_model=IngestionJob)
async def get_source_file_ingestion_job(
    document_id: str,
    file_id: str,
    job_id: str,
    request: Request,
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJob:
    await _admin_id(request)
    return await _resolve_ingestion_job(
        document_id=document_id,
        file_id=file_id,
        job_id=job_id,
        repository=ingestion_repository,
    )


@router.get("/{document_id}/files/{file_id}/ingestion-jobs/{job_id}/events", response_model=list[IngestionEvent])
async def list_source_file_ingestion_events(
    document_id: str,
    file_id: str,
    job_id: str,
    request: Request,
    after_sequence: int = 0,
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> list[IngestionEvent]:
    await _admin_id(request)
    if after_sequence < 0:
        raise HTTPException(status_code=422, detail="after_sequence must be non-negative")
    await _resolve_ingestion_job(
        document_id=document_id,
        file_id=file_id,
        job_id=job_id,
        repository=ingestion_repository,
    )
    return await ingestion_repository.list_events(job_id, after_sequence=after_sequence)


@router.post("/{document_id}/files/{file_id}/ingestion-jobs/{job_id}/steps/{step_name}/start", response_model=IngestionJob)
async def start_source_file_ingestion_step(
    document_id: str,
    file_id: str,
    job_id: str,
    step_name: IngestionStepName,
    body: IngestionStepStartRequest,
    request: Request,
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
    max_concurrent_jobs: int = Depends(get_ingestion_max_concurrent_jobs),
    lease_seconds: int = Depends(get_ingestion_lease_seconds),
) -> IngestionJob:
    await _admin_id(request)
    await _resolve_ingestion_job(
        document_id=document_id,
        file_id=file_id,
        job_id=job_id,
        repository=ingestion_repository,
    )
    try:
        started = await ingestion_repository.try_start_step(
            job_id,
            step_name=step_name,
            worker_id=body.worker_id,
            max_concurrent_jobs=max_concurrent_jobs,
            lease_seconds=lease_seconds,
            now=datetime.now(UTC),
        )
    except IngestionStateError as exc:
        raise _ingestion_transition_conflict(exc) from exc
    if started is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "ingestion_concurrency_limit", "message": "No ingestion worker slot is available or the job changed concurrently"},
        )
    return started


@router.post("/{document_id}/files/{file_id}/ingestion-jobs/{job_id}/lease", response_model=IngestionJob)
async def renew_source_file_ingestion_lease(
    document_id: str,
    file_id: str,
    job_id: str,
    body: IngestionStepStartRequest,
    request: Request,
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
    lease_seconds: int = Depends(get_ingestion_lease_seconds),
) -> IngestionJob:
    await _admin_id(request)
    await _resolve_ingestion_job(document_id=document_id, file_id=file_id, job_id=job_id, repository=ingestion_repository)
    renewed = await ingestion_repository.renew_lease(
        job_id,
        worker_id=body.worker_id,
        lease_seconds=lease_seconds,
        now=datetime.now(UTC),
    )
    if renewed is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "ingestion_lease_lost", "message": "The job is not running on this worker or its lease has expired"},
        )
    return renewed


@router.post("/{document_id}/files/{file_id}/ingestion-jobs/{job_id}/steps/{step_name}/complete", response_model=IngestionJob)
async def complete_source_file_ingestion_step(
    document_id: str,
    file_id: str,
    job_id: str,
    step_name: IngestionStepName,
    body: IngestionStepCompleteRequest,
    request: Request,
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJob:
    await _admin_id(request)
    job = await _resolve_ingestion_job(document_id=document_id, file_id=file_id, job_id=job_id, repository=ingestion_repository)
    try:
        updated, event = complete_step(job, step_name=step_name, output_ref=body.output_ref, now=datetime.now(UTC))
        await ingestion_repository.save(updated, event, expected_version=job.version)
    except (IngestionStateError, IngestionConcurrencyError) as exc:
        raise _ingestion_transition_conflict(exc) from exc
    return updated


@router.post("/{document_id}/files/{file_id}/ingestion-jobs/{job_id}/steps/{step_name}/fail", response_model=IngestionJob)
async def fail_source_file_ingestion_step(
    document_id: str,
    file_id: str,
    job_id: str,
    step_name: IngestionStepName,
    body: IngestionStepFailRequest,
    request: Request,
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJob:
    await _admin_id(request)
    job = await _resolve_ingestion_job(document_id=document_id, file_id=file_id, job_id=job_id, repository=ingestion_repository)
    try:
        updated, event = fail_step(
            job,
            step_name=step_name,
            error_code=body.error_code,
            error_message=body.error_message,
            retryable=body.retryable,
            now=datetime.now(UTC),
        )
        await ingestion_repository.save(updated, event, expected_version=job.version)
    except (IngestionStateError, IngestionConcurrencyError) as exc:
        raise _ingestion_transition_conflict(exc) from exc
    return updated


@router.post("/{document_id}/files/{file_id}/ingestion-jobs/{job_id}/steps/{step_name}/retry", response_model=IngestionJob)
async def retry_source_file_ingestion_step(
    document_id: str,
    file_id: str,
    job_id: str,
    step_name: IngestionStepName,
    request: Request,
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJob:
    admin_id = await _admin_id(request)
    job = await _resolve_ingestion_job(document_id=document_id, file_id=file_id, job_id=job_id, repository=ingestion_repository)
    try:
        updated, event = retry_failed_step(job, step_name=step_name, requested_by=admin_id, now=datetime.now(UTC))
        await ingestion_repository.save(updated, event, expected_version=job.version)
    except (IngestionStateError, IngestionConcurrencyError) as exc:
        raise _ingestion_transition_conflict(exc) from exc
    return updated


@router.post("/{document_id}/files/{file_id}/ingestion-jobs/{job_id}/cancel", response_model=IngestionJob)
async def cancel_source_file_ingestion_job(
    document_id: str,
    file_id: str,
    job_id: str,
    request: Request,
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJob:
    admin_id = await _admin_id(request)
    job = await _resolve_ingestion_job(document_id=document_id, file_id=file_id, job_id=job_id, repository=ingestion_repository)
    try:
        updated, event = cancel_job(job, requested_by=admin_id, now=datetime.now(UTC))
        if event is not None:
            await ingestion_repository.save(updated, event, expected_version=job.version)
    except (IngestionStateError, IngestionConcurrencyError) as exc:
        raise _ingestion_transition_conflict(exc) from exc
    return updated


@router.get("/{document_id}/files/{file_id}/review/queue", response_model=ReviewQueue)
async def get_source_file_review_queue(
    document_id: str,
    file_id: str,
    chunk_set_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    review_repository: ReviewRepository = Depends(get_review_repository),
) -> ReviewQueue:
    await _admin_id(request)
    await _resolve_ingestion_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    try:
        return await review_repository.get_queue(source_file_id=file_id, chunk_set_id=chunk_set_id)
    except ReviewTargetNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/files/{file_id}/review/decisions", response_model=list[ReviewRecord])
async def review_source_file_text(
    document_id: str,
    file_id: str,
    body: ReviewBatchRequest,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    review_repository: ReviewRepository = Depends(get_review_repository),
) -> list[ReviewRecord]:
    admin_id = await _admin_id(request)
    await _resolve_ingestion_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    try:
        return await review_repository.review_many(
            document_id=document_id,
            source_file_id=file_id,
            batch=body,
            reviewed_by=admin_id,
            reviewed_at=datetime.now(UTC),
            batch_id=f"review-batch-{uuid4().hex}",
        )
    except ReviewTargetNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "review_conflict", "message": str(exc)}) from exc


@router.get("/{document_id}/files/{file_id}/review/history", response_model=list[ReviewRecord])
async def list_source_file_review_history(
    document_id: str,
    file_id: str,
    request: Request,
    target_type: ReviewTargetType | None = None,
    target_id: str | None = None,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    review_repository: ReviewRepository = Depends(get_review_repository),
) -> list[ReviewRecord]:
    await _admin_id(request)
    await _resolve_ingestion_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    return await review_repository.list_records(
        source_file_id=file_id,
        target_type=target_type,
        target_id=target_id,
    )


@router.get("/{document_id}/files/{file_id}/review/chunks/{chunk_id}/gate", response_model=PublicationGateDecision)
async def get_source_file_chunk_publication_gate(
    document_id: str,
    file_id: str,
    chunk_id: str,
    request: Request,
    document_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    file_repository: SourceFileRepository = Depends(get_source_file_repository),
    review_repository: ReviewRepository = Depends(get_review_repository),
) -> PublicationGateDecision:
    await _admin_id(request)
    await _resolve_ingestion_source_file(
        document_id=document_id,
        file_id=file_id,
        document_repository=document_repository,
        file_repository=file_repository,
    )
    try:
        return await review_repository.publication_gate(source_file_id=file_id, chunk_id=chunk_id)
    except ReviewTargetNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/files/{file_id}/review/finalize", response_model=IngestionJob)
async def finalize_source_file_review(
    document_id: str,
    file_id: str,
    body: ReviewFinalizeRequest,
    request: Request,
    review_repository: ReviewRepository = Depends(get_review_repository),
    ingestion_repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJob:
    admin_id = await _admin_id(request)
    job = await _resolve_ingestion_job(
        document_id=document_id,
        file_id=file_id,
        job_id=body.ingestion_job_id,
        repository=ingestion_repository,
    )
    try:
        gate = await review_repository.chunk_set_publication_gate(
            source_file_id=file_id,
            chunk_set_id=body.chunk_set_id,
        )
    except ReviewTargetNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not gate.allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "review_gate_blocked",
                "message": "Every chunk and referenced clean page must be reviewed before finalization",
                "reasons": list(gate.reasons),
            },
        )
    now = datetime.now(UTC)
    try:
        running, started_event = begin_step(
            job,
            step_name=IngestionStepName.REVIEW,
            worker_id=f"reviewer:{admin_id}",
            now=now,
        )
        await ingestion_repository.save(running, started_event, expected_version=job.version)
        completed, completed_event = complete_step(
            running,
            step_name=IngestionStepName.REVIEW,
            output_ref=f"chunk-set:{body.chunk_set_id}",
            now=now,
        )
        await ingestion_repository.save(completed, completed_event, expected_version=running.version)
    except (IngestionStateError, IngestionConcurrencyError) as exc:
        raise _ingestion_transition_conflict(exc) from exc
    return completed


@public_router.get("/{document_id}/access", response_model=SourceAccessDecision)
async def check_source_access(
    document_id: str,
    use: AuthorizedUse,
    repository: SourceDocumentRepository = Depends(get_source_document_repository),
) -> SourceAccessDecision:
    document = await repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return evaluate_source_access(document, use=use)
    (ParsedDocument,)
    (ParsedDocumentRepository,)
