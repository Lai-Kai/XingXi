from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_backfills_hashes_and_marks_existing_duplicates(tmp_path):
    asyncio.run(_exercise_deduplication_migration(tmp_path))


async def _exercise_deduplication_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'dedupe-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0010_source_file_upload")
        async with engine.begin() as connection:
            for document_id in ("source-a", "source-b"):
                await connection.execute(
                    sa.text(
                        "INSERT INTO wu_source_documents "
                        "(id, title, edition, source_type, source_level, copyright_status, source_institution, holder, status, "
                        "authorization_status, visibility_scope, authorized_uses_json) "
                        "VALUES (:id, :id, 'test', 'archive', 'B', 'unknown', 'test', 'test', 'registered', "
                        "'unconfirmed', 'internal', '[]')"
                    ),
                    {"id": document_id},
                )
            for index, document_id in enumerate(("source-a", "source-b"), start=1):
                object_key = f"users/{document_id}/objects/original/aa/object-{index}"
                await connection.execute(
                    sa.text(
                        "INSERT INTO wu_object_metadata "
                        "(object_key, owner_id, kind, sha256, mime_type, size, backend, storage_uri, original_filename, created_at) "
                        "VALUES (:key, :owner, 'original', :sha, 'application/pdf', 10, 'local', :uri, :name, :created)"
                    ),
                    {
                        "key": object_key,
                        "owner": document_id,
                        "sha": "a" * 64,
                        "uri": f"file:///{index}",
                        "name": f"file-{index}.pdf",
                        "created": f"2026-07-21T00:00:0{index}+00:00",
                    },
                )
                await connection.execute(
                    sa.text("INSERT INTO wu_source_files (id, document_id, object_key, original_filename, mime_type, size, uploaded_by, uploaded_at) VALUES (:id, :document, :key, :name, 'application/pdf', 10, 'admin', :uploaded)"),
                    {
                        "id": f"file-{index}",
                        "document": document_id,
                        "key": object_key,
                        "name": f"file-{index}.pdf",
                        "uploaded": f"2026-07-21T00:00:0{index}+00:00",
                    },
                )

        await asyncio.to_thread(_upgrade, config, "0011_file_deduplication")

        async with engine.connect() as connection:
            rows = (await connection.execute(sa.text("SELECT id, sha256, duplicate_of_file_id, version_of_file_id FROM wu_source_files ORDER BY uploaded_at, id"))).all()
            indexes = await connection.run_sync(lambda sync: {index["name"]: index for index in sa.inspect(sync).get_indexes("wu_source_files")})
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()

        assert version == "0011_file_deduplication"
        assert rows == [
            ("file-1", "a" * 64, None, None),
            ("file-2", "a" * 64, "file-1", None),
        ]
        assert indexes["uq_wu_source_files_canonical_sha256"]["unique"] == 1
    finally:
        await engine.dispose()
