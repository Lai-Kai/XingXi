"""Store versioned raw and cleaned OCR text with change records.

Revision ID: 0014_raw_clean_text
Revises: 0013_scanned_source_ocr
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_raw_clean_text"
down_revision: str | Sequence[str] | None = "0013_scanned_source_ocr"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("wu_cleaned_ocr_pages"):
        op.create_table(
            "wu_cleaned_ocr_pages",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("ocr_attempt_id", sa.String(length=255), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("generation_number", sa.Integer(), nullable=False),
            sa.Column("raw_text", sa.Text(), nullable=False),
            sa.Column("raw_sha256", sa.String(length=64), nullable=False),
            sa.Column("clean_text", sa.Text(), nullable=False),
            sa.Column("clean_sha256", sa.String(length=64), nullable=False),
            sa.Column("rule_version", sa.String(length=128), nullable=False),
            sa.Column("script_conversion", sa.String(length=32), nullable=False),
            sa.Column("policy_json", sa.Text(), nullable=False),
            sa.Column("generated_by", sa.String(length=255), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("page_number >= 1", name="ck_wu_cleaned_ocr_page_number"),
            sa.CheckConstraint("generation_number >= 1", name="ck_wu_cleaned_ocr_generation_number"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["ocr_attempt_id"], ["wu_ocr_page_attempts.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("source_file_id", "page_number", "generation_number", name="uq_wu_cleaned_ocr_page_generation"),
        )
    _ensure_indexes(
        "wu_cleaned_ocr_pages",
        (
            ("ix_wu_cleaned_ocr_pages_source_file_id", ["source_file_id"]),
            ("ix_wu_cleaned_ocr_pages_ocr_attempt_id", ["ocr_attempt_id"]),
            ("ix_wu_cleaned_ocr_pages_page_number", ["page_number"]),
            ("ix_wu_cleaned_ocr_pages_raw_sha256", ["raw_sha256"]),
            ("ix_wu_cleaned_ocr_pages_clean_sha256", ["clean_sha256"]),
            ("ix_wu_cleaned_ocr_pages_rule_version", ["rule_version"]),
            ("ix_wu_cleaned_ocr_pages_generated_by", ["generated_by"]),
            ("ix_wu_cleaned_ocr_pages_generated_at", ["generated_at"]),
        ),
    )

    if not sa.inspect(bind).has_table("wu_text_cleaning_changes"):
        op.create_table(
            "wu_text_cleaning_changes",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("cleaned_page_id", sa.String(length=255), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("rule_id", sa.String(length=128), nullable=False),
            sa.Column("raw_start", sa.Integer(), nullable=False),
            sa.Column("raw_end", sa.Integer(), nullable=False),
            sa.Column("clean_start", sa.Integer(), nullable=False),
            sa.Column("clean_end", sa.Integer(), nullable=False),
            sa.Column("before", sa.Text(), nullable=False),
            sa.Column("after", sa.Text(), nullable=False),
            sa.CheckConstraint("sequence >= 0", name="ck_wu_text_cleaning_change_sequence"),
            sa.CheckConstraint("raw_start >= 0 AND raw_end >= raw_start", name="ck_wu_text_cleaning_change_raw_range"),
            sa.CheckConstraint("clean_start >= 0 AND clean_end >= clean_start", name="ck_wu_text_cleaning_change_clean_range"),
            sa.ForeignKeyConstraint(["cleaned_page_id"], ["wu_cleaned_ocr_pages.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("cleaned_page_id", "sequence", name="uq_wu_text_cleaning_change_order"),
        )
    _ensure_indexes(
        "wu_text_cleaning_changes",
        (
            ("ix_wu_text_cleaning_changes_cleaned_page_id", ["cleaned_page_id"]),
            ("ix_wu_text_cleaning_changes_rule_id", ["rule_id"]),
        ),
    )


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("wu_text_cleaning_changes"):
        op.drop_table("wu_text_cleaning_changes")
    if sa.inspect(bind).has_table("wu_cleaned_ocr_pages"):
        op.drop_table("wu_cleaned_ocr_pages")
