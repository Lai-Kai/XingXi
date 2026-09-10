"""SQLAlchemy rows for the Wu-culture evidence corpus."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DDL, BigInteger, CheckConstraint, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, LargeBinary, String, Text, UniqueConstraint, event
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from deerflow.persistence.base import Base


class VectorStorage(TypeDecorator):
    """Store float32 vectors as bytes on SQLite and pgvector on PostgreSQL."""

    impl = LargeBinary
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector())
        return dialect.type_descriptor(LargeBinary())

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None or dialect.name == "postgresql":
            return value
        if isinstance(value, bytes):
            return value
        import sqlite_vec

        return sqlite_vec.serialize_float32(value)


class SourceDocumentRow(Base):
    __tablename__ = "wu_source_documents"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    edition: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type_label: Mapped[str | None] = mapped_column(String(100))
    source_level: Mapped[str] = mapped_column(String(1), nullable=False, index=True)
    copyright_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_institution: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    holder: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="registered", index=True)
    authorization_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unconfirmed", index=True)
    authorization_basis: Mapped[str | None] = mapped_column(Text)
    authorization_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    visibility_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    authorized_uses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    authorization_proof_object_key: Mapped[str | None] = mapped_column(Text)
    file_hash: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceAuthorizationEventRow(Base):
    __tablename__ = "wu_source_authorization_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("wu_source_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    previous_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_copyright_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_copyright_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_visibility_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    new_authorized_uses_json: Mapped[str] = mapped_column(Text, nullable=False)
    authorization_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_proof_object_key: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class SourceFileRow(Base):
    __tablename__ = "wu_source_files"
    __table_args__ = (
        Index(
            "uq_wu_source_files_canonical_sha256",
            "sha256",
            unique=True,
            sqlite_where=sql_text("duplicate_of_file_id IS NULL"),
            postgresql_where=sql_text("duplicate_of_file_id IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("wu_source_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    object_key: Mapped[str] = mapped_column(
        Text,
        ForeignKey("wu_object_metadata.object_key", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    duplicate_of_file_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("wu_source_files.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    version_of_file_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("wu_source_files.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    uploaded_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ParsedDocumentRow(Base):
    __tablename__ = "wu_parsed_documents"
    __table_args__ = (
        UniqueConstraint("source_file_id", name="uq_wu_parsed_document_source_file"),
        CheckConstraint("page_count >= 1", name="ck_wu_parsed_document_page_count"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_file_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("wu_source_files.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default=sql_text("'{}'"))
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ParsedBlockRow(Base):
    __tablename__ = "wu_parsed_blocks"
    __table_args__ = (
        UniqueConstraint("parsed_document_id", "block_index", name="uq_wu_parsed_block_order"),
        CheckConstraint("page_number >= 1", name="ck_wu_parsed_block_page_number"),
        CheckConstraint("block_index >= 0", name="ck_wu_parsed_block_index"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    parsed_document_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("wu_parsed_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default=sql_text("'{}'"))


class OcrPageAttemptRow(Base):
    __tablename__ = "wu_ocr_page_attempts"
    __table_args__ = (
        UniqueConstraint("source_file_id", "page_number", "attempt_number", name="uq_wu_ocr_page_attempt_number"),
        CheckConstraint("page_number >= 1", name="ck_wu_ocr_page_attempt_page_number"),
        CheckConstraint("attempt_number >= 1", name="ck_wu_ocr_page_attempt_number"),
        CheckConstraint(
            "(image_sha256 IS NULL AND image_width IS NULL AND image_height IS NULL) OR (image_sha256 IS NOT NULL AND image_width >= 1 AND image_height >= 1)",
            name="ck_wu_ocr_page_attempt_image_size",
        ),
        CheckConstraint("mean_confidence IS NULL OR (mean_confidence >= 0 AND mean_confidence <= 1)", name="ck_wu_ocr_page_attempt_confidence"),
        CheckConstraint("rotation_degrees IN (0, 90, 180, 270)", name="ck_wu_ocr_page_attempt_rotation"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    folio_label: Mapped[str | None] = mapped_column(String(255))
    page_image_object_key: Mapped[str | None] = mapped_column(Text)
    image_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    languages_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    mean_confidence: Mapped[float | None] = mapped_column(Float)
    rotation_degrees: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=sql_text("0"))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class OcrRegionRow(Base):
    __tablename__ = "wu_ocr_regions"
    __table_args__ = (
        UniqueConstraint("attempt_id", "region_index", name="uq_wu_ocr_region_order"),
        CheckConstraint("region_index >= 0", name="ck_wu_ocr_region_index"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_wu_ocr_region_confidence"),
        CheckConstraint("x >= 0 AND y >= 0 AND width > 0 AND height > 0 AND x + width <= 1 AND y + height <= 1", name="ck_wu_ocr_region_bounds"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_ocr_page_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    region_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)


class CleanedOcrPageRow(Base):
    __tablename__ = "wu_cleaned_ocr_pages"
    __table_args__ = (
        UniqueConstraint("source_file_id", "page_number", "generation_number", name="uq_wu_cleaned_ocr_page_generation"),
        CheckConstraint("page_number >= 1", name="ck_wu_cleaned_ocr_page_number"),
        CheckConstraint("generation_number >= 1", name="ck_wu_cleaned_ocr_generation_number"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    ocr_attempt_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_ocr_page_attempts.id", ondelete="RESTRICT"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    generation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    clean_text: Mapped[str] = mapped_column(Text, nullable=False)
    clean_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    script_conversion: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_json: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default=sql_text("'pending'"), index=True)
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class TextCleaningChangeRow(Base):
    __tablename__ = "wu_text_cleaning_changes"
    __table_args__ = (
        UniqueConstraint("cleaned_page_id", "sequence", name="uq_wu_text_cleaning_change_order"),
        CheckConstraint("sequence >= 0", name="ck_wu_text_cleaning_change_sequence"),
        CheckConstraint("raw_start >= 0 AND raw_end >= raw_start", name="ck_wu_text_cleaning_change_raw_range"),
        CheckConstraint("clean_start >= 0 AND clean_end >= clean_start", name="ck_wu_text_cleaning_change_clean_range"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    cleaned_page_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_cleaned_ocr_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_start: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_end: Mapped[int] = mapped_column(Integer, nullable=False)
    clean_start: Mapped[int] = mapped_column(Integer, nullable=False)
    clean_end: Mapped[int] = mapped_column(Integer, nullable=False)
    before: Mapped[str] = mapped_column(Text, nullable=False)
    after: Mapped[str] = mapped_column(Text, nullable=False)


class ChunkSetRow(Base):
    __tablename__ = "wu_chunk_sets"
    __table_args__ = (UniqueConstraint("source_file_id", "split_version", name="uq_wu_chunk_set_file_version"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    split_version: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    policy_json: Mapped[str] = mapped_column(Text, nullable=False)
    structure_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class TextChunkRow(Base):
    __tablename__ = "wu_text_chunks"
    __table_args__ = (
        UniqueConstraint("id", "document_id", name="uq_wu_text_chunk_id_document"),
        UniqueConstraint("chunk_set_id", "chunk_index", name="uq_wu_text_chunk_set_order"),
        CheckConstraint("page_start >= 1", name="ck_wu_text_chunk_page_start"),
        CheckConstraint("page_end >= page_start", name="ck_wu_text_chunk_page_range"),
        CheckConstraint("chunk_index >= 0", name="ck_wu_text_chunk_index"),
        CheckConstraint("paragraph_char_start IS NULL OR paragraph_char_start >= 0", name="ck_wu_text_chunk_char_start"),
        CheckConstraint("paragraph_char_end IS NULL OR paragraph_char_end > paragraph_char_start", name="ck_wu_text_chunk_char_range"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("wu_source_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_file_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), index=True)
    chunk_set_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_chunk_sets.id", ondelete="CASCADE"), index=True)
    split_version: Mapped[str] = mapped_column(String(128), nullable=False, default="legacy-v0", server_default=sql_text("'legacy-v0'"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=sql_text("0"))
    volume: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)
    item: Mapped[str | None] = mapped_column(Text)
    paragraph: Mapped[str | None] = mapped_column(Text)
    paragraph_index: Mapped[int | None] = mapped_column(Integer)
    paragraph_char_start: Mapped[int | None] = mapped_column(Integer)
    paragraph_char_end: Mapped[int | None] = mapped_column(Integer)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    cleaned_page_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default=sql_text("'[]'"))
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)


class ReviewRecordRow(Base):
    __tablename__ = "wu_review_records"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "revision", name="uq_wu_review_target_revision"),
        CheckConstraint("revision >= 1", name="ck_wu_review_record_revision"),
        CheckConstraint("target_type IN ('page', 'chunk')", name="ck_wu_review_record_target_type"),
        CheckConstraint("decision IN ('reviewed', 'rejected', 'disputed')", name="ck_wu_review_record_decision"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    batch_id: Mapped[str | None] = mapped_column(String(255), index=True)
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class KnowledgeReleaseRow(Base):
    __tablename__ = "wu_knowledge_releases"
    __table_args__ = (
        UniqueConstraint("version_number", name="uq_wu_knowledge_release_version"),
        UniqueConstraint("manifest_sha256", name="uq_wu_knowledge_release_manifest"),
        CheckConstraint("version_number >= 1", name="ck_wu_knowledge_release_version"),
        CheckConstraint(
            "status IN ('preparing', 'ready', 'failed', 'active')",
            name="ck_wu_knowledge_release_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    release_notes: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="public", server_default="public")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="preparing", server_default="preparing", index=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), index=True)
    failure_message: Mapped[str | None] = mapped_column(Text)
    preparation_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=sql_text("0"))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class KnowledgeReleaseItemRow(Base):
    __tablename__ = "wu_knowledge_release_items"
    __table_args__ = (
        UniqueConstraint("release_id", "chunk_id", name="uq_wu_knowledge_release_chunk"),
        CheckConstraint("ordinal >= 0", name="ck_wu_knowledge_release_item_ordinal"),
    )

    release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="CASCADE"), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    chunk_set_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_chunk_sets.id", ondelete="RESTRICT"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_text_chunks.id", ondelete="RESTRICT"), nullable=False, index=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    cleaned_page_ids_json: Mapped[str] = mapped_column(Text, nullable=False)


class KnowledgeReleaseStateRow(Base):
    __tablename__ = "wu_knowledge_release_state"
    __table_args__ = (CheckConstraint("state_version >= 0", name="ck_wu_knowledge_release_state_version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    active_release_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="RESTRICT"), nullable=True, index=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=sql_text("0"))
    updated_by: Mapped[str | None] = mapped_column(String(255), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeReleaseEventRow(Base):
    __tablename__ = "wu_knowledge_release_events"
    __table_args__ = (
        CheckConstraint("state_version >= 1", name="ck_wu_knowledge_release_event_state_version"),
        CheckConstraint("action IN ('publish', 'activate', 'rollback')", name="ck_wu_knowledge_release_event_action"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    previous_release_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="RESTRICT"))
    new_release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="RESTRICT"), nullable=False, index=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class FullTextDocumentRow(Base):
    __tablename__ = "wu_fulltext_documents"
    __table_args__ = (
        UniqueConstraint("release_id", "chunk_id", name="uq_wu_fulltext_release_chunk"),
        CheckConstraint("page_start >= 1", name="ck_wu_fulltext_page_start"),
        CheckConstraint("page_end >= page_start", name="ck_wu_fulltext_page_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="CASCADE"), nullable=False, index=True)
    release_version: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    chunk_set_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_chunk_sets.id", ondelete="RESTRICT"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_text_chunks.id", ondelete="RESTRICT"), nullable=False, index=True)
    document_title: Mapped[str] = mapped_column(Text, nullable=False)
    edition: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_level: Mapped[str] = mapped_column(String(1), nullable=False)
    volume: Mapped[str | None] = mapped_column(Text)
    item: Mapped[str | None] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    clean_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_title: Mapped[str] = mapped_column(Text, nullable=False)
    search_headings: Mapped[str] = mapped_column(Text, nullable=False)
    search_body: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class FullTextIndexStateRow(Base):
    __tablename__ = "wu_fulltext_index_states"
    __table_args__ = (
        CheckConstraint("document_count >= 1", name="ck_wu_fulltext_index_document_count"),
        CheckConstraint("status = 'ready'", name="ck_wu_fulltext_index_status"),
    )

    release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="CASCADE"), primary_key=True)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready", server_default=sql_text("'ready'"))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class SearchFilterMetadataRow(Base):
    __tablename__ = "wu_search_filter_metadata"
    __table_args__ = (
        CheckConstraint("review_status IN ('pending', 'reviewed', 'disputed', 'rejected')", name="ck_wu_search_filter_review_status"),
        CheckConstraint("spatial_confidence IS NULL OR (spatial_confidence >= 0 AND spatial_confidence <= 1)", name="ck_wu_search_filter_spatial_confidence"),
    )

    release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_text_chunks.id", ondelete="RESTRICT"), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    edition: Mapped[str | None] = mapped_column(Text, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_level: Mapped[str] = mapped_column(String(1), nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    spatial_confidence: Mapped[float | None] = mapped_column(Float, index=True)


class SearchFilterFacetRow(Base):
    __tablename__ = "wu_search_filter_facets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_id", "chunk_id"],
            ["wu_search_filter_metadata.release_id", "wu_search_filter_metadata.chunk_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("facet_type IN ('dynasty', 'entity_type')", name="ck_wu_search_filter_facet_type"),
        Index("ix_wu_search_filter_facet_lookup", "facet_type", "facet_value", "release_id", "chunk_id"),
    )

    release_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    facet_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    facet_value: Mapped[str] = mapped_column(String(64), primary_key=True)


class AliasIndexRow(Base):
    __tablename__ = "wu_alias_index"
    __table_args__ = (
        UniqueConstraint("release_id", "entity_id", "normalized_alias", name="uq_wu_alias_release_entity_name"),
        CheckConstraint("alias_type IN ('historical_name', 'colloquial_name', 'character_variant', 'modern_name')", name="ck_wu_alias_type"),
        CheckConstraint("review_status IN ('pending', 'reviewed', 'disputed', 'rejected')", name="ck_wu_alias_review_status"),
        CheckConstraint("alias_length >= 1", name="ck_wu_alias_length"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alias_length: Mapped[int] = mapped_column(Integer, nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class AliasDynastyRow(Base):
    __tablename__ = "wu_alias_dynasties"

    alias_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_alias_index.id", ondelete="CASCADE"), primary_key=True)
    dynasty: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)


class AliasEvidenceRow(Base):
    __tablename__ = "wu_alias_evidence"

    alias_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_alias_index.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_evidence.id", ondelete="RESTRICT"), primary_key=True, index=True)


class VectorIndexVersionRow(Base):
    __tablename__ = "wu_vector_index_versions"
    __table_args__ = (
        CheckConstraint("dimensions >= 1", name="ck_wu_vector_index_dimensions"),
        CheckConstraint("item_count >= 0", name="ck_wu_vector_index_item_count"),
        CheckConstraint("base_state_version >= 0", name="ck_wu_vector_index_base_state_version"),
        CheckConstraint("status IN ('building', 'ready', 'failed')", name="ck_wu_vector_index_status"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="CASCADE"), nullable=False, index=True)
    release_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=sql_text("0"))
    base_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VectorEmbeddingRow(Base):
    __tablename__ = "wu_vector_embeddings"
    __table_args__ = (
        UniqueConstraint("index_version_id", "chunk_id", name="uq_wu_vector_index_chunk"),
        CheckConstraint("dimensions >= 1", name="ck_wu_vector_embedding_dimensions"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_version_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_vector_index_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_text_chunks.id", ondelete="RESTRICT"), nullable=False, index=True)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[object] = mapped_column(VectorStorage(), nullable=False)


class VectorIndexStateRow(Base):
    __tablename__ = "wu_vector_index_states"
    __table_args__ = (CheckConstraint("state_version >= 0", name="ck_wu_vector_index_state_version"),)

    release_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="CASCADE"), primary_key=True)
    active_index_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_vector_index_versions.id", ondelete="RESTRICT"), index=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=sql_text("0"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


event.listen(
    FullTextDocumentRow.__table__,
    "after_create",
    DDL("CREATE VIRTUAL TABLE IF NOT EXISTS wu_fulltext_fts USING fts5(search_title, search_headings, search_body, content='wu_fulltext_documents', content_rowid='id', tokenize='trigram')").execute_if(dialect="sqlite"),
)
event.listen(
    FullTextDocumentRow.__table__,
    "before_drop",
    DDL("DROP TABLE IF EXISTS wu_fulltext_fts").execute_if(dialect="sqlite"),
)


class IngestionJobRow(Base):
    __tablename__ = "wu_ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("created_by", "idempotency_key", name="uq_wu_ingestion_job_actor_idempotency"),
        CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_wu_ingestion_job_progress"),
        CheckConstraint("version >= 1", name="ck_wu_ingestion_job_version"),
        CheckConstraint("event_sequence >= 1", name="ck_wu_ingestion_job_event_sequence"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    current_step: Mapped[str | None] = mapped_column(String(32), index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    owner_worker_id: Mapped[str | None] = mapped_column(String(255), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionStepRow(Base):
    __tablename__ = "wu_ingestion_steps"
    __table_args__ = (CheckConstraint("attempt_count >= 0", name="ck_wu_ingestion_step_attempt_count"),)

    job_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_ingestion_jobs.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(255), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_ref: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(128), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=sql_text("1"))


class IngestionEventRow(Base):
    __tablename__ = "wu_ingestion_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_wu_ingestion_event_sequence"),
        CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_wu_ingestion_event_progress"),
    )

    job_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_ingestion_jobs.id", ondelete="CASCADE"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    job_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    step_name: Mapped[str | None] = mapped_column(String(32), index=True)
    step_status: Mapped[str | None] = mapped_column(String(32))
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class EvidenceRow(Base):
    __tablename__ = "wu_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "document_id"],
            ["wu_text_chunks.id", "wu_text_chunks.document_id"],
            name="fk_wu_evidence_chunk_document",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("wu_source_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    source_level: Mapped[str] = mapped_column(String(1), nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)


WU_CULTURE_TABLES = [
    SourceDocumentRow.__table__,
    SourceAuthorizationEventRow.__table__,
    SourceFileRow.__table__,
    ParsedDocumentRow.__table__,
    ParsedBlockRow.__table__,
    OcrPageAttemptRow.__table__,
    OcrRegionRow.__table__,
    CleanedOcrPageRow.__table__,
    TextCleaningChangeRow.__table__,
    ChunkSetRow.__table__,
    TextChunkRow.__table__,
    ReviewRecordRow.__table__,
    KnowledgeReleaseRow.__table__,
    KnowledgeReleaseItemRow.__table__,
    KnowledgeReleaseStateRow.__table__,
    KnowledgeReleaseEventRow.__table__,
    FullTextDocumentRow.__table__,
    FullTextIndexStateRow.__table__,
    SearchFilterMetadataRow.__table__,
    SearchFilterFacetRow.__table__,
    AliasIndexRow.__table__,
    AliasDynastyRow.__table__,
    AliasEvidenceRow.__table__,
    VectorIndexVersionRow.__table__,
    VectorEmbeddingRow.__table__,
    VectorIndexStateRow.__table__,
    IngestionJobRow.__table__,
    IngestionStepRow.__table__,
    IngestionEventRow.__table__,
    EvidenceRow.__table__,
]


class WuEntityRow(Base):
    __tablename__ = "wu_entities"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('person','family','place','waterway','bridge','building','garden','relic','organization','work','event')",
            name="ck_wu_entities_type",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'disputed', 'rejected')",
            name="ck_wu_entities_review_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dynasty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extant_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    release_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WuEntityEvidenceRow(Base):
    __tablename__ = "wu_entity_evidence"

    entity_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_entities.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_evidence.id", ondelete="RESTRICT"), primary_key=True, index=True)


class WuRelationRow(Base):
    __tablename__ = "wu_relations"
    __table_args__ = (
        UniqueConstraint("subject_id", "relation_type", "object_id", "release_id", name="uq_wu_relation_edge_release"),
        CheckConstraint(
            "relation_type IN ('located_in','built_by','repaired_in','crosses','related_to','sibling_of','spouse_of','parent_of','lived_in','visited','born_in','worked_at','studied_at','died_at','composed_at','mentioned_in_poetry','documented_in')",
            name="ck_wu_relations_type",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_wu_relations_confidence"),
        CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'disputed', 'rejected')",
            name="ck_wu_relations_review_status",
        ),
        CheckConstraint("subject_id <> object_id", name="ck_wu_relations_distinct_endpoints"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_entities.id", ondelete="RESTRICT"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    object_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_entities.id", ondelete="RESTRICT"), nullable=False, index=True)
    start_time: Mapped[str | None] = mapped_column(String(128), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_inferred: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=sql_text("false"))
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    release_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CorpusImportBatchRow(Base):
    __tablename__ = "wu_corpus_import_batches"
    __table_args__ = (CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_wu_corpus_import_batch_status"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    corpus_root_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CorpusImportItemRow(Base):
    __tablename__ = "wu_corpus_import_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "bundle_id", name="uq_wu_corpus_import_item_bundle"),
        CheckConstraint("status IN ('completed', 'failed')", name="ck_wu_corpus_import_item_status"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_corpus_import_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    bundle_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False)
    chunk_set_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_chunk_sets.id", ondelete="RESTRICT"), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_issue_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    imported_by: Mapped[str] = mapped_column(String(255), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)


class CorpusQualityIssueRow(Base):
    __tablename__ = "wu_corpus_quality_issues"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    import_item_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_corpus_import_items.id", ondelete="CASCADE"), nullable=False, index=True)
    bundle_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    physical_page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    folio_label: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)


class WuRelationEvidenceRow(Base):
    __tablename__ = "wu_relation_evidence"

    relation_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_relations.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_evidence.id", ondelete="RESTRICT"), primary_key=True, index=True)


class WuHistoricalEventRow(Base):
    __tablename__ = "wu_historical_events"
    __table_args__ = (
        CheckConstraint("time_certainty IN ('exact','approximate','unknown')", name="ck_wu_events_time_certainty"),
        CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'disputed', 'rejected')",
            name="ck_wu_events_review_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_time: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    end_time: Mapped[str | None] = mapped_column(String(128), nullable=True)
    time_certainty: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    place_entity_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_entities.id", ondelete="SET NULL"), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_inferred: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=sql_text("false"))
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    release_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WuEventParticipantRow(Base):
    __tablename__ = "wu_event_participants"

    event_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_historical_events.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_entities.id", ondelete="RESTRICT"), primary_key=True, index=True)


class WuEventEvidenceRow(Base):
    __tablename__ = "wu_event_evidence"

    event_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_historical_events.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_evidence.id", ondelete="RESTRICT"), primary_key=True, index=True)


class WuGeoFeatureRow(Base):
    __tablename__ = "wu_geo_features"
    __table_args__ = (
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_wu_geo_longitude"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_wu_geo_latitude"),
        CheckConstraint(
            "confidence IN ('exact','approximate','speculative')",
            name="ck_wu_geo_confidence",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'disputed', 'rejected')",
            name="ck_wu_geo_review_status",
        ),
        CheckConstraint(
            "geometry_type IN ('point','uncertainty_radius','historical_area')",
            name="ck_wu_geo_geometry_type",
        ),
        CheckConstraint(
            "uncertainty_radius_m IS NULL OR "
            "(uncertainty_radius_m >= 10 AND uncertainty_radius_m <= 100000)",
            name="ck_wu_geo_uncertainty_radius",
        ),
    )

    entity_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_entities.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(24), nullable=False, default="point", server_default="point")
    uncertainty_radius_m: Mapped[float | None] = mapped_column(Float)
    area_coordinates_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    extent_source: Mapped[str | None] = mapped_column(String(24))
    extent_basis: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    release_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("wu_knowledge_releases.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WuGeoEvidenceRow(Base):
    __tablename__ = "wu_geo_evidence"

    entity_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_geo_features.entity_id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(255), ForeignKey("wu_evidence.id", ondelete="RESTRICT"), primary_key=True, index=True)


WU_CULTURE_TABLES.extend(
    [
        CorpusImportBatchRow.__table__,
        CorpusImportItemRow.__table__,
        CorpusQualityIssueRow.__table__,
        WuEntityRow.__table__,
        WuEntityEvidenceRow.__table__,
        WuRelationRow.__table__,
        WuRelationEvidenceRow.__table__,
        WuHistoricalEventRow.__table__,
        WuEventParticipantRow.__table__,
        WuEventEvidenceRow.__table__,
        WuGeoFeatureRow.__table__,
        WuGeoEvidenceRow.__table__,
    ]
)
