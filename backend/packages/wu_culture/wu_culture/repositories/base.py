from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from wu_culture.ingestion import IngestionJob
from wu_culture.models import EvidenceRecord, SourceAuthorizationEvent, SourceDocument, SourceFile
from wu_culture.parsing import ParsedDocument
from wu_culture.storage import StoredObject


class DuplicateSourceFileError(ValueError):
    def __init__(self, existing_file: SourceFile) -> None:
        super().__init__("Source file content already exists")
        self.existing_file = existing_file


class EvidenceRepository(Protocol):
    """Read-only evidence source used by retrieval services."""

    def iter_evidence(self) -> Iterable[EvidenceRecord]: ...

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None: ...


class AsyncEvidenceRepository(Protocol):
    """Asynchronous evidence source used by database-backed retrieval."""

    async def list_evidence(self) -> Sequence[EvidenceRecord]: ...

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None: ...


class SourceDocumentRepository(Protocol):
    async def create(self, document: SourceDocument) -> SourceDocument: ...

    async def get(self, document_id: str) -> SourceDocument | None: ...

    async def list(self) -> Sequence[SourceDocument]: ...

    async def update(self, document: SourceDocument) -> SourceDocument | None: ...

    async def update_authorization(
        self,
        document: SourceDocument,
        event: SourceAuthorizationEvent,
    ) -> SourceDocument | None: ...

    async def list_authorization_events(self, document_id: str) -> Sequence[SourceAuthorizationEvent]: ...


@dataclass(frozen=True)
class SourceDocumentLibraryFile:
    file: SourceFile
    ingestion_job: IngestionJob | None


@dataclass(frozen=True)
class SourceDocumentLibraryItem:
    document: SourceDocument
    files: tuple[SourceDocumentLibraryFile, ...]


class SourceDocumentLibraryRepository(Protocol):
    async def list_library_page(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[SourceDocumentLibraryItem], int]: ...


class SourceFileRepository(Protocol):
    async def attach(self, source_file: SourceFile, metadata: StoredObject) -> SourceFile: ...

    async def list_for_document(self, document_id: str) -> Sequence[SourceFile]: ...

    async def list_all(self) -> Sequence[SourceFile]: ...

    async def find_by_sha256(self, sha256: str) -> SourceFile | None: ...

    async def get(self, file_id: str) -> SourceFile | None: ...

    async def find_by_document_and_filename(self, document_id: str, filename: str) -> SourceFile | None: ...


class ParsedDocumentRepository(Protocol):
    async def save(self, document: ParsedDocument) -> ParsedDocument: ...

    async def get_by_source_file_id(self, source_file_id: str) -> ParsedDocument | None: ...
