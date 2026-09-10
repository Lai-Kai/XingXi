from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import CopyrightStatus, SourceDocument, SourceFile, SourceLevel, SourceType
from wu_culture.repositories import DuplicateSourceFileError
from wu_culture.storage import ObjectKind, StoredObject

from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture import SourceDocumentRow, SourceFileRow, SqlSourceDocumentRepository, SqlSourceFileRepository


def test_source_file_and_object_metadata_persist_atomically(tmp_path):
    asyncio.run(_exercise_source_file_repository(tmp_path))


def test_concurrent_canonical_uploads_allow_only_one_file_per_hash(tmp_path):
    asyncio.run(_exercise_concurrent_deduplication(tmp_path))


async def _exercise_source_file_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source-files.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[ObjectMetadataRow.__table__, SourceDocumentRow.__table__, SourceFileRow.__table__],
            )
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    document = SourceDocument(
        id="source-upload-sql",
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
        object_key="users/source-upload-sql/objects/original/ab/" + "a" * 64,
        owner_id=document.id,
        kind=ObjectKind.ORIGINAL,
        sha256="a" * 64,
        mime_type="application/pdf",
        size=123,
        backend="local",
        storage_uri="file:///objects/source.pdf",
        original_filename="source.pdf",
        created_at=now,
    )
    source_file = SourceFile(
        id="source-file-sql",
        document_id=document.id,
        object_key=metadata.object_key,
        original_filename="source.pdf",
        mime_type="application/pdf",
        size=123,
        sha256="a" * 64,
        uploaded_by="admin-1",
        uploaded_at=now,
    )

    try:
        await SqlSourceDocumentRepository(session_factory).create(document)
        await SqlSourceFileRepository(session_factory).attach(source_file, metadata)
        restored = await SqlSourceFileRepository(session_factory).list_for_document(document.id)

        assert restored == [source_file]
        async with session_factory() as session:
            assert await session.get(ObjectMetadataRow, metadata.object_key) is not None
            assert await session.get(SourceFileRow, source_file.id) is not None
    finally:
        await engine.dispose()


async def _exercise_concurrent_deduplication(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source-file-race.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    documents = [
        SourceDocument(
            id=f"source-race-{index}",
            title=f"Race {index}",
            edition="test",
            source_institution="test",
            source_type=SourceType.ARCHIVE,
            source_level=SourceLevel.B,
            copyright_status=CopyrightStatus.UNKNOWN,
            holder="test",
            created_by="admin",
            created_at=now,
            updated_by="admin",
            updated_at=now,
        )
        for index in (1, 2)
    ]
    repository = SqlSourceFileRepository(session_factory)
    try:
        document_repository = SqlSourceDocumentRepository(session_factory)
        for document in documents:
            await document_repository.create(document)
        metadata = [
            StoredObject(
                object_key=f"users/{document.id}/objects/original/aa/object-{index}",
                owner_id=document.id,
                kind=ObjectKind.ORIGINAL,
                sha256="b" * 64,
                mime_type="application/pdf",
                size=10,
                backend="local",
                storage_uri=f"file:///{index}",
                original_filename=f"race-{index}.pdf",
                created_at=now,
            )
            for index, document in enumerate(documents, start=1)
        ]
        files = [
            SourceFile(
                id=f"source-file-race-{index}",
                document_id=document.id,
                object_key=stored.object_key,
                original_filename=f"race-{index}.pdf",
                mime_type="application/pdf",
                size=10,
                sha256=stored.sha256,
                uploaded_by="admin",
                uploaded_at=now,
            )
            for index, (document, stored) in enumerate(zip(documents, metadata, strict=True), start=1)
        ]

        results = await asyncio.gather(
            *(repository.attach(source_file, stored) for source_file, stored in zip(files, metadata, strict=True)),
            return_exceptions=True,
        )

        successes = [result for result in results if isinstance(result, SourceFile)]
        duplicates = [result for result in results if isinstance(result, DuplicateSourceFileError)]
        assert len(successes) == 1
        assert len(duplicates) == 1
        assert duplicates[0].existing_file.id == successes[0].id
        assert (await repository.find_by_sha256("b" * 64)).id == successes[0].id
    finally:
        await engine.dispose()
