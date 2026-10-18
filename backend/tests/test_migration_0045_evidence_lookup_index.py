"""Release joins must not rescan a document's Evidence for every Chunk."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import load_only

from deerflow.persistence.base import Base
from deerflow.persistence.wu_culture.model import WU_CULTURE_TABLES, EvidenceRow, KnowledgeReleaseItemRow, KnowledgeReleaseRow, SourceDocumentRow, TextChunkRow

INDEX = "ix_wu_evidence_chunk_document"


def _seed(connection, size=1600):
    connection.execute(SourceDocumentRow.__table__.insert(), {"id": "doc", "title": "测试方志", "source_type": "gazetteer", "source_level": "A", "copyright_status": "public_domain"})
    connection.execute(
        KnowledgeReleaseRow.__table__.insert(),
        {"id": "release", "version_number": 1, "release_notes": "test", "status": "active", "scope": "public", "manifest_sha256": "a" * 64, "created_by": "admin", "created_at": datetime.now(UTC)},
    )
    connection.execute(
        TextChunkRow.__table__.insert(),
        [{"id": str(i), "document_id": "doc", "original_text": "史料正文", "normalized_text": "史料正文", "page_start": i + 1, "page_end": i + 1, "review_status": "reviewed"} for i in range(size)],
    )
    connection.execute(EvidenceRow.__table__.insert(), [{"id": str(i), "document_id": "doc", "chunk_id": str(i), "quote": "史料引文", "source_level": "A", "review_status": "reviewed"} for i in range(size)])
    connection.execute(
        KnowledgeReleaseItemRow.__table__.insert(),
        [{"release_id": "release", "ordinal": i, "document_id": "doc", "source_file_id": "file", "chunk_set_id": "set", "chunk_id": str(i), "content_sha256": "b" * 64, "cleaned_page_ids_json": "[]"} for i in range(size)],
    )


def _read_with_work_budget(connection):
    # Keep the deployed query shape covered during rolling upgrades as well as
    # metadata-only reads. A VM instruction budget detects quadratic scans
    # deterministically without depending on machine speed or timing assertions.
    # Match an existing installation where the document index was created last;
    # SQLite otherwise may happen to pick the equally estimated Chunk index.
    connection.exec_driver_sql("DROP INDEX ix_wu_evidence_document_id")
    connection.exec_driver_sql("CREATE INDEX ix_wu_evidence_document_id ON wu_evidence (document_id)")
    statement = (
        select(EvidenceRow, SourceDocumentRow, TextChunkRow)
        .join(SourceDocumentRow, SourceDocumentRow.id == EvidenceRow.document_id)
        .join(TextChunkRow, TextChunkRow.id == EvidenceRow.chunk_id)
        .join(KnowledgeReleaseItemRow, (KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id) & (KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id))
        .where(KnowledgeReleaseItemRow.release_id == "release")
        .options(load_only(TextChunkRow.id, TextChunkRow.page_start, TextChunkRow.page_end, TextChunkRow.volume, TextChunkRow.review_status))
        .order_by(EvidenceRow.id)
    )
    sqlite = connection.connection.driver_connection
    sqlite.set_progress_handler(lambda: 1, 500_000)
    try:
        assert len(connection.execute(statement).all()) == 1600
    finally:
        sqlite.set_progress_handler(None, 0)


def _revision(connection):
    path = Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations/versions/0045_evidence_lookup_index.py"
    spec = importlib.util.spec_from_file_location("evidence_lookup_index", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(connection))
    return module


def test_fresh_schema_bounds_release_evidence_join():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            Base.metadata.create_all(connection, tables=WU_CULTURE_TABLES)
            _seed(connection)
            _read_with_work_budget(connection)
    finally:
        engine.dispose()


def test_index_upgrade_is_repeatable_and_downgrade_preserves_evidence():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            Base.metadata.create_all(connection, tables=WU_CULTURE_TABLES)
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {INDEX}")
            _seed(connection)
            revision = _revision(connection)
            revision.upgrade()
            revision.upgrade()
            index = next(index for index in inspect(connection).get_indexes("wu_evidence") if index["name"] == INDEX)
            assert index["column_names"] == ["chunk_id", "document_id"]
            _read_with_work_budget(connection)
            revision.downgrade()
            revision.downgrade()
            assert INDEX not in {index["name"] for index in inspect(connection).get_indexes("wu_evidence")}
            assert connection.exec_driver_sql("SELECT count(*) FROM wu_evidence").scalar_one() == 1600
            assert connection.exec_driver_sql("SELECT count(*) FROM wu_knowledge_release_items").scalar_one() == 1600
    finally:
        engine.dispose()
