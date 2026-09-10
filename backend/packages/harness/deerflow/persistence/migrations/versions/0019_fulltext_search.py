"""Add release-scoped Chinese full-text search indexes.

Revision ID: 0019_fulltext_search
Revises: 0018_knowledge_releases
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_fulltext_search"
down_revision: str | Sequence[str] | None = "0018_knowledge_releases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("wu_fulltext_documents"):
        op.create_table(
            "wu_fulltext_documents",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("external_id", sa.String(length=255), nullable=False, unique=True),
            sa.Column("release_id", sa.String(length=255), nullable=False),
            sa.Column("release_version", sa.String(length=32), nullable=False),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("chunk_set_id", sa.String(length=255), nullable=False),
            sa.Column("chunk_id", sa.String(length=255), nullable=False),
            sa.Column("document_title", sa.Text(), nullable=False),
            sa.Column("edition", sa.Text(), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_level", sa.String(length=1), nullable=False),
            sa.Column("volume", sa.Text(), nullable=True),
            sa.Column("item", sa.Text(), nullable=True),
            sa.Column("page_start", sa.Integer(), nullable=False),
            sa.Column("page_end", sa.Integer(), nullable=False),
            sa.Column("raw_text", sa.Text(), nullable=False),
            sa.Column("clean_text", sa.Text(), nullable=False),
            sa.Column("search_title", sa.Text(), nullable=False),
            sa.Column("search_headings", sa.Text(), nullable=False),
            sa.Column("search_body", sa.Text(), nullable=False),
            sa.Column("search_text", sa.Text(), nullable=False),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["chunk_set_id"], ["wu_chunk_sets.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["chunk_id"], ["wu_text_chunks.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("release_id", "chunk_id", name="uq_wu_fulltext_release_chunk"),
            sa.CheckConstraint("page_start >= 1", name="ck_wu_fulltext_page_start"),
            sa.CheckConstraint("page_end >= page_start", name="ck_wu_fulltext_page_range"),
        )
    _ensure_indexes(
        "wu_fulltext_documents",
        tuple(
            (f"ix_wu_fulltext_documents_{column}", [column])
            for column in (
                "release_id",
                "release_version",
                "document_id",
                "source_file_id",
                "chunk_set_id",
                "chunk_id",
                "source_type",
                "indexed_at",
            )
        ),
    )

    if not sa.inspect(op.get_bind()).has_table("wu_fulltext_index_states"):
        op.create_table(
            "wu_fulltext_index_states",
            sa.Column("release_id", sa.String(length=255), primary_key=True),
            sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
            sa.Column("document_count", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ready'")),
            sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="CASCADE"),
            sa.CheckConstraint("document_count >= 1", name="ck_wu_fulltext_index_document_count"),
            sa.CheckConstraint("status = 'ready'", name="ck_wu_fulltext_index_status"),
        )
    _ensure_indexes("wu_fulltext_index_states", (("ix_wu_fulltext_index_states_indexed_at", ["indexed_at"]),))

    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("CREATE VIRTUAL TABLE IF NOT EXISTS wu_fulltext_fts USING fts5(search_title, search_headings, search_body, content='wu_fulltext_documents', content_rowid='id', tokenize='trigram')")
    elif dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute("CREATE INDEX IF NOT EXISTS ix_wu_fulltext_documents_search_text_trgm ON wu_fulltext_documents USING gin (search_text gin_trgm_ops)")


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TABLE IF EXISTS wu_fulltext_fts")
    elif dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_wu_fulltext_documents_search_text_trgm")
    op.drop_table("wu_fulltext_index_states")
    op.drop_table("wu_fulltext_documents")
