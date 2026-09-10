"""Wu-culture evidence persistence.

Revision ID: 0006_wu_culture_persistence
Revises: 0005_run_stop_reason
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_wu_culture_persistence"
down_revision: str | Sequence[str] | None = "0005_run_stop_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _ensure_index(table_name: str, index_name: str, columns: list[str]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    if not _table_exists("wu_source_documents"):
        op.create_table(
            "wu_source_documents",
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("edition", sa.Text(), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_level", sa.String(length=1), nullable=False),
            sa.Column("copyright_status", sa.String(length=32), nullable=False),
            sa.Column("file_hash", sa.String(length=255), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("wu_source_documents", "ix_wu_source_documents_source_level", ["source_level"])

    if not _table_exists("wu_text_chunks"):
        op.create_table(
            "wu_text_chunks",
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("volume", sa.Text(), nullable=True),
            sa.Column("section", sa.Text(), nullable=True),
            sa.Column("paragraph", sa.Text(), nullable=True),
            sa.Column("original_text", sa.Text(), nullable=False),
            sa.Column("normalized_text", sa.Text(), nullable=False),
            sa.Column("page_start", sa.Integer(), nullable=False),
            sa.Column("page_end", sa.Integer(), nullable=False),
            sa.Column("review_status", sa.String(length=20), nullable=False),
            sa.CheckConstraint("page_end >= page_start", name="ck_wu_text_chunk_page_range"),
            sa.CheckConstraint("page_start >= 1", name="ck_wu_text_chunk_page_start"),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("id", "document_id", name="uq_wu_text_chunk_id_document"),
        )
    _ensure_index("wu_text_chunks", "ix_wu_text_chunks_document_id", ["document_id"])
    _ensure_index("wu_text_chunks", "ix_wu_text_chunks_review_status", ["review_status"])

    if not _table_exists("wu_evidence"):
        op.create_table(
            "wu_evidence",
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("chunk_id", sa.String(length=255), nullable=False),
            sa.Column("quote", sa.Text(), nullable=False),
            sa.Column("source_level", sa.String(length=1), nullable=False),
            sa.Column("review_status", sa.String(length=20), nullable=False),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["chunk_id", "document_id"],
                ["wu_text_chunks.id", "wu_text_chunks.document_id"],
                name="fk_wu_evidence_chunk_document",
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("wu_evidence", "ix_wu_evidence_chunk_id", ["chunk_id"])
    _ensure_index("wu_evidence", "ix_wu_evidence_document_id", ["document_id"])
    _ensure_index("wu_evidence", "ix_wu_evidence_review_status", ["review_status"])
    _ensure_index("wu_evidence", "ix_wu_evidence_source_level", ["source_level"])


def downgrade() -> None:
    op.drop_index("ix_wu_evidence_source_level", table_name="wu_evidence")
    op.drop_index("ix_wu_evidence_review_status", table_name="wu_evidence")
    op.drop_index("ix_wu_evidence_document_id", table_name="wu_evidence")
    op.drop_index("ix_wu_evidence_chunk_id", table_name="wu_evidence")
    op.drop_table("wu_evidence")

    op.drop_index("ix_wu_text_chunks_review_status", table_name="wu_text_chunks")
    op.drop_index("ix_wu_text_chunks_document_id", table_name="wu_text_chunks")
    op.drop_table("wu_text_chunks")

    op.drop_index("ix_wu_source_documents_source_level", table_name="wu_source_documents")
    op.drop_table("wu_source_documents")
