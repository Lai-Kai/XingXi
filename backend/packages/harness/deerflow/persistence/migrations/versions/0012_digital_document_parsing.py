"""Store structured digital-document parsing results.

Revision ID: 0012_digital_document_parsing
Revises: 0011_file_deduplication
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_digital_document_parsing"
down_revision: str | Sequence[str] | None = "0011_file_deduplication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("wu_parsed_documents"):
        op.create_table(
            "wu_parsed_documents",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("parser_name", sa.String(length=64), nullable=False),
            sa.Column("parser_version", sa.String(length=32), nullable=False),
            sa.Column("mime_type", sa.String(length=255), nullable=False),
            sa.Column("page_count", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("page_count >= 1", name="ck_wu_parsed_document_page_count"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("source_file_id", name="uq_wu_parsed_document_source_file"),
        )
    _ensure_indexes(
        "wu_parsed_documents",
        (
            ("ix_wu_parsed_documents_source_file_id", ["source_file_id"]),
            ("ix_wu_parsed_documents_parsed_at", ["parsed_at"]),
        ),
    )

    if not sa.inspect(bind).has_table("wu_parsed_blocks"):
        op.create_table(
            "wu_parsed_blocks",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("parsed_document_id", sa.String(length=255), nullable=False),
            sa.Column("block_type", sa.String(length=32), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("block_index", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.CheckConstraint("page_number >= 1", name="ck_wu_parsed_block_page_number"),
            sa.CheckConstraint("block_index >= 0", name="ck_wu_parsed_block_index"),
            sa.ForeignKeyConstraint(["parsed_document_id"], ["wu_parsed_documents.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("parsed_document_id", "block_index", name="uq_wu_parsed_block_order"),
        )
    _ensure_indexes(
        "wu_parsed_blocks",
        (
            ("ix_wu_parsed_blocks_parsed_document_id", ["parsed_document_id"]),
            ("ix_wu_parsed_blocks_block_type", ["block_type"]),
            ("ix_wu_parsed_blocks_page_number", ["page_number"]),
        ),
    )


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("wu_parsed_blocks"):
        op.drop_table("wu_parsed_blocks")
    if sa.inspect(bind).has_table("wu_parsed_documents"):
        op.drop_table("wu_parsed_documents")
