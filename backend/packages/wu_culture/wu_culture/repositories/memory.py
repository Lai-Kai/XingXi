from __future__ import annotations

from collections.abc import Iterable

from wu_culture.models import EvidenceRecord, SourceAuthorizationEvent, SourceDocument, SourceFile
from wu_culture.parsing import ParsedDocument
from wu_culture.storage import StoredObject

from .base import DuplicateSourceFileError


class InMemoryEvidenceRepository:
    """Deterministic repository for tests and an empty local runtime."""

    def __init__(self, records: Iterable[EvidenceRecord] = ()) -> None:
        self._records = tuple(records)

    def get_evidence(self, evidence_id: str):
        for record in self._records:
            if record.evidence.id == evidence_id:
                return record
        return None

    def iter_evidence(self) -> tuple[EvidenceRecord, ...]:
        return self._records


class InMemorySourceDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, SourceDocument] = {}
        self._authorization_events: dict[str, list[SourceAuthorizationEvent]] = {}

    async def create(self, document: SourceDocument) -> SourceDocument:
        if document.id in self._documents:
            raise ValueError(f"Source document {document.id!r} already exists")
        self._documents[document.id] = document
        return document

    async def get(self, document_id: str) -> SourceDocument | None:
        return self._documents.get(document_id)

    async def list(self) -> tuple[SourceDocument, ...]:
        return tuple(self._documents.values())

    async def update(self, document: SourceDocument) -> SourceDocument | None:
        if document.id not in self._documents:
            return None
        self._documents[document.id] = document
        return document

    async def update_authorization(
        self,
        document: SourceDocument,
        event: SourceAuthorizationEvent,
    ) -> SourceDocument | None:
        if document.id not in self._documents:
            return None
        self._documents[document.id] = document
        self._authorization_events.setdefault(document.id, []).append(event)
        return document

    async def list_authorization_events(self, document_id: str) -> tuple[SourceAuthorizationEvent, ...]:
        return tuple(self._authorization_events.get(document_id, ()))


class InMemorySourceFileRepository:
    def __init__(self) -> None:
        self._files: dict[str, SourceFile] = {}
        self._metadata: dict[str, StoredObject] = {}

    async def attach(self, source_file: SourceFile, metadata: StoredObject) -> SourceFile:
        if source_file.id in self._files:
            raise ValueError(f"Source file {source_file.id!r} already exists")
        existing = await self.find_by_sha256(metadata.sha256)
        if existing is not None and source_file.duplicate_of_file_id is None:
            raise DuplicateSourceFileError(existing)
        self._files[source_file.id] = source_file
        self._metadata[source_file.id] = metadata
        return source_file

    async def list_for_document(self, document_id: str) -> tuple[SourceFile, ...]:
        return tuple(source_file for source_file in self._files.values() if source_file.document_id == document_id)

    async def find_by_sha256(self, sha256: str) -> SourceFile | None:
        return next(
            (source_file for file_id, source_file in self._files.items() if self._metadata[file_id].sha256 == sha256),
            None,
        )

    async def get(self, file_id: str) -> SourceFile | None:
        return self._files.get(file_id)

    async def find_by_document_and_filename(self, document_id: str, filename: str) -> SourceFile | None:
        return next(
            (source_file for source_file in self._files.values() if source_file.document_id == document_id and source_file.original_filename == filename),
            None,
        )


class InMemoryParsedDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, ParsedDocument] = {}

    async def save(self, document: ParsedDocument) -> ParsedDocument:
        if document.source_file_id in self._documents:
            raise ValueError(f"Source file {document.source_file_id!r} already has a parsed document")
        self._documents[document.source_file_id] = document
        return document

    async def get_by_source_file_id(self, source_file_id: str) -> ParsedDocument | None:
        return self._documents.get(source_file_id)
