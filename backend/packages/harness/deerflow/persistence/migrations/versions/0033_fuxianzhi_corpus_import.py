"""Add resumable fuxianzhi imports and precomputed OCR provenance.

Revision ID: 0033_fuxianzhi_corpus_import
Revises: 0032_research_project_records
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_fuxianzhi_corpus_import"
down_revision = "0032_research_project_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("wu_ocr_page_attempts") as batch:
        batch.add_column(sa.Column("folio_label", sa.String(255), nullable=True))
        batch.drop_constraint("ck_wu_ocr_page_attempt_image_size", type_="check")
        batch.alter_column("image_sha256", existing_type=sa.String(64), nullable=True)
        batch.alter_column("image_width", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("image_height", existing_type=sa.Integer(), nullable=True)
        batch.create_check_constraint(
            "ck_wu_ocr_page_attempt_image_size",
            "(image_sha256 IS NULL AND image_width IS NULL AND image_height IS NULL) OR (image_sha256 IS NOT NULL AND image_width >= 1 AND image_height >= 1)",
        )

    op.create_table(
        "wu_corpus_import_batches",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("corpus_root_id", sa.String(255), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_wu_corpus_import_batch_status"),
    )
    op.create_index("ix_wu_corpus_import_batches_root", "wu_corpus_import_batches", ["corpus_root_id"])
    op.create_index("ix_wu_corpus_import_batches_status", "wu_corpus_import_batches", ["status"])
    op.create_index("ix_wu_corpus_import_batches_created_by", "wu_corpus_import_batches", ["created_by"])

    op.create_table(
        "wu_corpus_import_items",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("batch_id", sa.String(255), sa.ForeignKey("wu_corpus_import_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bundle_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(255), sa.ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_file_id", sa.String(255), sa.ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("chunk_set_id", sa.String(255), sa.ForeignKey("wu_chunk_sets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("quality_issue_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("imported_by", sa.String(255), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("batch_id", "bundle_id", name="uq_wu_corpus_import_item_bundle"),
        sa.CheckConstraint("status IN ('completed', 'failed')", name="ck_wu_corpus_import_item_status"),
    )
    op.create_index("ix_wu_corpus_import_items_batch", "wu_corpus_import_items", ["batch_id"])
    op.create_index("ix_wu_corpus_import_items_bundle", "wu_corpus_import_items", ["bundle_id"])
    op.create_index("ix_wu_corpus_import_items_status", "wu_corpus_import_items", ["status"])

    op.create_table(
        "wu_corpus_quality_issues",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("import_item_id", sa.String(255), sa.ForeignKey("wu_corpus_import_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bundle_id", sa.String(64), nullable=False),
        sa.Column("source_file_id", sa.String(255), sa.ForeignKey("wu_source_files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("physical_page_number", sa.Integer(), nullable=False),
        sa.Column("folio_label", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("ix_wu_corpus_quality_item", "wu_corpus_quality_issues", ["import_item_id"])
    op.create_index("ix_wu_corpus_quality_bundle", "wu_corpus_quality_issues", ["bundle_id"])
    op.create_index("ix_wu_corpus_quality_source_file", "wu_corpus_quality_issues", ["source_file_id"])
    op.create_index("ix_wu_corpus_quality_code", "wu_corpus_quality_issues", ["code"])
    op.create_index("ix_wu_corpus_quality_severity", "wu_corpus_quality_issues", ["severity"])


def downgrade() -> None:
    op.drop_table("wu_corpus_quality_issues")
    op.drop_table("wu_corpus_import_items")
    op.drop_table("wu_corpus_import_batches")
    with op.batch_alter_table("wu_ocr_page_attempts") as batch:
        batch.drop_constraint("ck_wu_ocr_page_attempt_image_size", type_="check")
        batch.alter_column("image_sha256", existing_type=sa.String(64), nullable=False)
        batch.alter_column("image_width", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("image_height", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("folio_label")
        batch.create_check_constraint(
            "ck_wu_ocr_page_attempt_image_size",
            "image_width >= 1 AND image_height >= 1",
        )
