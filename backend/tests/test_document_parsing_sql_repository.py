from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import CopyrightStatus, SourceDocument, SourceFile, SourceLevel, SourceType
from wu_culture.parsing import DocumentParseRequest, ParsedDocument, parse_document
from wu_culture.storage import ObjectKind, StoredObject

from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture import (
    ParsedBlockRow,
    ParsedDocumentRow,
    SourceDocumentRow,
    SourceFileRow,
    SqlParsedDocumentRepository,
    SqlSourceDocumentRepository,
    SqlSourceFileRepository,
)


def test_parsed_document_round_trips_with_ordered_page_blocks(tmp_path):
    asyncio.run(_exercise_parsed_document_repository(tmp_path))


async def _exercise_parsed_document_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'parsed-document.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):  # noqa: ANN001, ARG001
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[
                    ObjectMetadataRow.__table__,
                    SourceDocumentRow.__table__,
                    SourceFileRow.__table__,
                    ParsedDocumentRow.__table__,
                    ParsedBlockRow.__table__,
                ],
            )
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    document = SourceDocument(
        id="source-parse-sql",
        title="木渎小志",
        edition="测试版",
        source_institution="测试机构",
        source_type=SourceType.GAZETTEER,
        source_level=SourceLevel.A,
        copyright_status=CopyrightStatus.UNKNOWN,
        holder="测试资料组",
        created_by="admin-1",
        created_at=now,
        updated_by="admin-1",
        updated_at=now,
    )
    metadata = StoredObject(
        object_key="users/source-parse-sql/objects/original/ab/" + "a" * 64,
        owner_id=document.id,
        kind=ObjectKind.ORIGINAL,
        sha256="a" * 64,
        mime_type="text/plain",
        size=12,
        backend="local",
        storage_uri="file:///objects/source.txt",
        original_filename="source.txt",
        created_at=now,
    )
    source_file = SourceFile(
        id="source-file-parse-sql",
        document_id=document.id,
        object_key=metadata.object_key,
        original_filename="source.txt",
        mime_type="text/plain",
        size=12,
        sha256="a" * 64,
        uploaded_by="admin-1",
        uploaded_at=now,
    )
    content = parse_document(
        DocumentParseRequest(
            filename="source.txt",
            mime_type="text/plain",
            content="第一段。\n\n第二段。".encode(),
        )
    )
    parsed = ParsedDocument(
        id="parsed-source-file-parse-sql",
        source_file_id=source_file.id,
        mime_type=source_file.mime_type,
        parsed_at=now,
        **content.model_dump(),
    )

    try:
        await SqlSourceDocumentRepository(session_factory).create(document)
        await SqlSourceFileRepository(session_factory).attach(source_file, metadata)
        repository = SqlParsedDocumentRepository(session_factory)
        await repository.save(parsed)

        assert await repository.get_by_source_file_id(source_file.id) == parsed
    finally:
        await engine.dispose()
