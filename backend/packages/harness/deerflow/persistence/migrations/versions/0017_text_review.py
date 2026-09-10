"""Add append-only page and chunk human review records.

Revision ID: 0017_text_review
Revises: 0016_ingestion_jobs
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_text_review"
down_revision: str | Sequence[str] | None = "0016_ingestion_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    cleaned_columns = {column["name"] for column in sa.inspect(bind).get_columns("wu_cleaned_ocr_pages")}
    if "review_status" not in cleaned_columns:
        with op.batch_alter_table("wu_cleaned_ocr_pages") as batch:
            batch.add_column(sa.Column("review_status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")))
    _ensure_indexes("wu_cleaned_ocr_pages", (("ix_wu_cleaned_ocr_pages_review_status", ["review_status"]),))

    if not sa.inspect(bind).has_table("wu_review_records"):
        op.create_table(
            "wu_review_records",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("target_type", sa.String(length=20), nullable=False),
            sa.Column("target_id", sa.String(length=255), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("previous_status", sa.String(length=20), nullable=False),
            sa.Column("decision", sa.String(length=20), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("batch_id", sa.String(length=255), nullable=True),
            sa.Column("reviewed_by", sa.String(length=255), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("target_type", "target_id", "revision", name="uq_wu_review_target_revision"),
            sa.CheckConstraint("revision >= 1", name="ck_wu_review_record_revision"),
            sa.CheckConstraint("target_type IN ('page', 'chunk')", name="ck_wu_review_record_target_type"),
            sa.CheckConstraint("decision IN ('reviewed', 'rejected', 'disputed')", name="ck_wu_review_record_decision"),
        )
    _ensure_indexes(
        "wu_review_records",
        (
            ("ix_wu_review_records_document_id", ["document_id"]),
            ("ix_wu_review_records_source_file_id", ["source_file_id"]),
            ("ix_wu_review_records_target_type", ["target_type"]),
            ("ix_wu_review_records_target_id", ["target_id"]),
            ("ix_wu_review_records_decision", ["decision"]),
            ("ix_wu_review_records_batch_id", ["batch_id"]),
            ("ix_wu_review_records_reviewed_by", ["reviewed_by"]),
            ("ix_wu_review_records_reviewed_at", ["reviewed_at"]),
        ),
    )


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    op.drop_table("wu_review_records")
    op.drop_index("ix_wu_cleaned_ocr_pages_review_status", table_name="wu_cleaned_ocr_pages")
    with op.batch_alter_table("wu_cleaned_ocr_pages") as batch:
        batch.drop_column("review_status")
