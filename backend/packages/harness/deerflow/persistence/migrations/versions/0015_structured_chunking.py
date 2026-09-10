"""Add versioned structure-aware chunk sets.

Revision ID: 0015_structured_chunking
Revises: 0014_raw_clean_text
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_structured_chunking"
down_revision: str | Sequence[str] | None = "0014_raw_clean_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("wu_chunk_sets"):
        op.create_table(
            "wu_chunk_sets",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("split_version", sa.String(length=128), nullable=False),
            sa.Column("policy_json", sa.Text(), nullable=False),
            sa.Column("structure_json", sa.Text(), nullable=False),
            sa.Column("input_sha256", sa.String(length=64), nullable=False),
            sa.Column("generated_by", sa.String(length=255), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("source_file_id", "split_version", name="uq_wu_chunk_set_file_version"),
        )
    _ensure_indexes(
        "wu_chunk_sets",
        (
            ("ix_wu_chunk_sets_document_id", ["document_id"]),
            ("ix_wu_chunk_sets_source_file_id", ["source_file_id"]),
            ("ix_wu_chunk_sets_split_version", ["split_version"]),
            ("ix_wu_chunk_sets_input_sha256", ["input_sha256"]),
            ("ix_wu_chunk_sets_generated_by", ["generated_by"]),
            ("ix_wu_chunk_sets_generated_at", ["generated_at"]),
        ),
    )

    chunk_columns = {column["name"] for column in sa.inspect(bind).get_columns("wu_text_chunks")}
    with op.batch_alter_table("wu_text_chunks") as batch:
        if "source_file_id" not in chunk_columns:
            batch.add_column(sa.Column("source_file_id", sa.String(length=255), nullable=True))
        if "chunk_set_id" not in chunk_columns:
            batch.add_column(sa.Column("chunk_set_id", sa.String(length=255), nullable=True))
        if "split_version" not in chunk_columns:
            batch.add_column(sa.Column("split_version", sa.String(length=128), nullable=False, server_default=sa.text("'legacy-v0'")))
        if "chunk_index" not in chunk_columns:
            batch.add_column(sa.Column("chunk_index", sa.Integer(), nullable=False, server_default=sa.text("0")))
        if "item" not in chunk_columns:
            batch.add_column(sa.Column("item", sa.Text(), nullable=True))
        if "paragraph_index" not in chunk_columns:
            batch.add_column(sa.Column("paragraph_index", sa.Integer(), nullable=True))
        if "paragraph_char_start" not in chunk_columns:
            batch.add_column(sa.Column("paragraph_char_start", sa.Integer(), nullable=True))
        if "paragraph_char_end" not in chunk_columns:
            batch.add_column(sa.Column("paragraph_char_end", sa.Integer(), nullable=True))
        if "cleaned_page_ids_json" not in chunk_columns:
            batch.add_column(sa.Column("cleaned_page_ids_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")))
        if "content_sha256" not in chunk_columns:
            batch.add_column(sa.Column("content_sha256", sa.String(length=64), nullable=True))
        if "source_file_id" not in chunk_columns:
            batch.create_foreign_key("fk_wu_text_chunks_source_file", "wu_source_files", ["source_file_id"], ["id"], ondelete="RESTRICT")
        if "chunk_set_id" not in chunk_columns:
            batch.create_foreign_key("fk_wu_text_chunks_chunk_set", "wu_chunk_sets", ["chunk_set_id"], ["id"], ondelete="CASCADE")
            batch.create_unique_constraint("uq_wu_text_chunk_set_order", ["chunk_set_id", "chunk_index"])
        batch.create_check_constraint("ck_wu_text_chunk_index", "chunk_index >= 0")
        batch.create_check_constraint("ck_wu_text_chunk_char_start", "paragraph_char_start IS NULL OR paragraph_char_start >= 0")
        batch.create_check_constraint("ck_wu_text_chunk_char_range", "paragraph_char_end IS NULL OR paragraph_char_end > paragraph_char_start")

    _ensure_indexes(
        "wu_text_chunks",
        (
            ("ix_wu_text_chunks_source_file_id", ["source_file_id"]),
            ("ix_wu_text_chunks_chunk_set_id", ["chunk_set_id"]),
            ("ix_wu_text_chunks_split_version", ["split_version"]),
            ("ix_wu_text_chunks_content_sha256", ["content_sha256"]),
        ),
    )


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    for index_name in (
        "ix_wu_text_chunks_content_sha256",
        "ix_wu_text_chunks_split_version",
        "ix_wu_text_chunks_chunk_set_id",
        "ix_wu_text_chunks_source_file_id",
    ):
        op.drop_index(index_name, table_name="wu_text_chunks")
    with op.batch_alter_table("wu_text_chunks") as batch:
        batch.drop_constraint("ck_wu_text_chunk_char_range", type_="check")
        batch.drop_constraint("ck_wu_text_chunk_char_start", type_="check")
        batch.drop_constraint("ck_wu_text_chunk_index", type_="check")
        batch.drop_constraint("uq_wu_text_chunk_set_order", type_="unique")
        batch.drop_constraint("fk_wu_text_chunks_chunk_set", type_="foreignkey")
        batch.drop_constraint("fk_wu_text_chunks_source_file", type_="foreignkey")
        for column_name in (
            "content_sha256",
            "cleaned_page_ids_json",
            "paragraph_char_end",
            "paragraph_char_start",
            "paragraph_index",
            "item",
            "chunk_index",
            "split_version",
            "chunk_set_id",
            "source_file_id",
        ):
            batch.drop_column(column_name)
    op.drop_table("wu_chunk_sets")
