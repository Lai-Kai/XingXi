from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import CopyrightStatus, SourceDocument, SourceFile, SourceLevel, SourceType
from wu_culture.ingestion import create_ingestion_job
from wu_culture.storage import ObjectKind, StoredObject

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade, bootstrap_schema
from deerflow.persistence.wu_culture import (
    SqlIngestionJobRepository,
    SqlSourceDocumentRepository,
    SqlSourceFileRepository,
)

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


def test_old_database_upgrade_repairs_ingestion_event_fk_and_creates_job(tmp_path) -> None:
    asyncio.run(_exercise_old_database_upgrade(tmp_path))


def test_startup_rejects_ingestion_fk_drift_after_migrations(tmp_path) -> None:
    asyncio.run(_exercise_startup_fk_check(tmp_path))


async def _exercise_old_database_upgrade(tmp_path) -> None:
    database = tmp_path / "old-ingestion.db"
    engine = _engine(database)
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0035_spatial_extents")
    finally:
        await engine.dispose()

    _replace_event_table_with_wrong_parent(database)
    engine = _engine(database)
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0036_ingestion_fk_compatibility")
        async with engine.connect() as connection:
            foreign_keys = await connection.run_sync(lambda sync: sa.inspect(sync).get_foreign_keys("wu_ingestion_events"))
        assert _foreign_key_contract(foreign_keys) == {("job_id", "wu_ingestion_jobs", "id", "CASCADE")}

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        await _create_source_file(session_factory)
        repository = SqlIngestionJobRepository(session_factory)
        job, created_event = create_ingestion_job(
            job_id="job-after-upgrade",
            document_id="document-after-upgrade",
            source_file_id="file-after-upgrade",
            idempotency_key="upgrade-regression",
            created_by="admin-1",
            now=NOW,
        )
        stored, created = await repository.create(job, created_event)
        assert created is True
        assert stored == job
        assert [item.event_type for item in await repository.list_events(job.id)] == ["job_created"]

        bad_event = created_event.model_copy(update={"job_id": "missing-parent"})
        bad_job = job.model_copy(update={"id": "job-must-rollback", "idempotency_key": "rollback-regression"})
        with pytest.raises(IntegrityError):
            await repository.create(bad_job, bad_event)
        async with engine.connect() as connection:
            counts = []
            for table in ("wu_ingestion_steps", "wu_ingestion_events"):
                counts.append(
                    await connection.execute(
                        sa.text(f"SELECT count(*) FROM {table} WHERE job_id = :job_id"),
                        {"job_id": bad_job.id},
                    )
                )
            counts = [result.scalar_one() for result in counts]
            job_count = (
                await connection.execute(
                    sa.text("SELECT count(*) FROM wu_ingestion_jobs WHERE id = :job_id"),
                    {"job_id": bad_job.id},
                )
            ).scalar_one()
        assert (job_count, *counts) == (0, 0, 0)
    finally:
        await engine.dispose()


async def _exercise_startup_fk_check(tmp_path) -> None:
    database = tmp_path / "drifted-ingestion.db"
    engine = _engine(database)
    try:
        await bootstrap_schema(engine, backend="sqlite")
    finally:
        await engine.dispose()

    _replace_event_table_with_wrong_parent(database)
    engine = _engine(database)
    try:
        with pytest.raises(RuntimeError, match="ingestion foreign-key contract"):
            await bootstrap_schema(engine, backend="sqlite")
    finally:
        await engine.dispose()


def _engine(database):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):  # noqa: ANN001, ARG001
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _replace_event_table_with_wrong_parent(database) -> None:
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.executescript(
            """
            ALTER TABLE wu_ingestion_events RENAME TO wu_ingestion_events_old;
            CREATE TABLE wu_ingestion_events (
                job_id VARCHAR(255) NOT NULL,
                sequence INTEGER NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                job_status VARCHAR(32) NOT NULL,
                step_name VARCHAR(32),
                step_status VARCHAR(32),
                progress_percent INTEGER NOT NULL,
                error_code VARCHAR(128),
                error_message TEXT,
                actor_id VARCHAR(255) NOT NULL,
                created_at DATETIME NOT NULL,
                PRIMARY KEY (job_id, sequence),
                FOREIGN KEY(job_id) REFERENCES wu_source_files(id) ON DELETE CASCADE,
                CHECK (sequence >= 1),
                CHECK (progress_percent >= 0 AND progress_percent <= 100)
            );
            INSERT INTO wu_ingestion_events SELECT * FROM wu_ingestion_events_old;
            DROP TABLE wu_ingestion_events_old;
            """
        )
        connection.commit()
    finally:
        connection.close()


def _foreign_key_contract(foreign_keys: list[dict]) -> set[tuple[str, str, str, str]]:
    return {
        (
            item["constrained_columns"][0],
            item["referred_table"],
            item["referred_columns"][0],
            item["options"].get("ondelete", "NO ACTION").upper(),
        )
        for item in foreign_keys
    }


async def _create_source_file(session_factory) -> None:  # noqa: ANN001
    await SqlSourceDocumentRepository(session_factory).create(
        SourceDocument(
            id="document-after-upgrade",
            title="旧库升级测试",
            edition="测试版",
            source_type=SourceType.GAZETTEER,
            source_level=SourceLevel.A,
            copyright_status=CopyrightStatus.UNKNOWN,
            source_institution="测试机构",
            holder="测试机构",
            created_by="admin-1",
            created_at=NOW,
            updated_by="admin-1",
            updated_at=NOW,
        )
    )
    source_file = SourceFile(
        id="file-after-upgrade",
        document_id="document-after-upgrade",
        object_key="sources/document-after-upgrade/file.pdf",
        original_filename="旧库.pdf",
        sha256="f" * 64,
        mime_type="application/pdf",
        size=100,
        uploaded_by="admin-1",
        uploaded_at=NOW,
    )
    await SqlSourceFileRepository(session_factory).attach(
        source_file,
        StoredObject(
            object_key=source_file.object_key,
            owner_id=source_file.document_id,
            kind=ObjectKind.ORIGINAL,
            sha256=source_file.sha256,
            mime_type=source_file.mime_type,
            size=source_file.size,
            backend="local",
            storage_uri="file:///objects/old-db.pdf",
            original_filename=source_file.original_filename,
            created_at=NOW,
        ),
    )
