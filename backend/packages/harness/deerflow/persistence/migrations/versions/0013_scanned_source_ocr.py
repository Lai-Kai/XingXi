"""Store append-only scanned-source OCR page attempts and regions.

Revision ID: 0013_scanned_source_ocr
Revises: 0012_digital_document_parsing
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_scanned_source_ocr"
down_revision: str | Sequence[str] | None = "0012_digital_document_parsing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("wu_ocr_page_attempts"):
        op.create_table(
            "wu_ocr_page_attempts",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("page_image_object_key", sa.Text()),
            sa.Column("image_sha256", sa.String(length=64), nullable=False),
            sa.Column("image_width", sa.Integer(), nullable=False),
            sa.Column("image_height", sa.Integer(), nullable=False),
            sa.Column("provider_name", sa.String(length=64), nullable=False),
            sa.Column("model_name", sa.String(length=255), nullable=False),
            sa.Column("languages_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("raw_text", sa.Text()),
            sa.Column("mean_confidence", sa.Float()),
            sa.Column("rotation_degrees", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("error_code", sa.String(length=64)),
            sa.Column("error_message", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("page_number >= 1", name="ck_wu_ocr_page_attempt_page_number"),
            sa.CheckConstraint("attempt_number >= 1", name="ck_wu_ocr_page_attempt_number"),
            sa.CheckConstraint("image_width >= 1 AND image_height >= 1", name="ck_wu_ocr_page_attempt_image_size"),
            sa.CheckConstraint("mean_confidence IS NULL OR (mean_confidence >= 0 AND mean_confidence <= 1)", name="ck_wu_ocr_page_attempt_confidence"),
            sa.CheckConstraint("rotation_degrees IN (0, 90, 180, 270)", name="ck_wu_ocr_page_attempt_rotation"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("source_file_id", "page_number", "attempt_number", name="uq_wu_ocr_page_attempt_number"),
        )
    _ensure_indexes(
        "wu_ocr_page_attempts",
        (
            ("ix_wu_ocr_page_attempts_source_file_id", ["source_file_id"]),
            ("ix_wu_ocr_page_attempts_page_number", ["page_number"]),
            ("ix_wu_ocr_page_attempts_image_sha256", ["image_sha256"]),
            ("ix_wu_ocr_page_attempts_status", ["status"]),
            ("ix_wu_ocr_page_attempts_created_at", ["created_at"]),
        ),
    )

    if not sa.inspect(bind).has_table("wu_ocr_regions"):
        op.create_table(
            "wu_ocr_regions",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("attempt_id", sa.String(length=255), nullable=False),
            sa.Column("region_index", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("x", sa.Float(), nullable=False),
            sa.Column("y", sa.Float(), nullable=False),
            sa.Column("width", sa.Float(), nullable=False),
            sa.Column("height", sa.Float(), nullable=False),
            sa.CheckConstraint("region_index >= 0", name="ck_wu_ocr_region_index"),
            sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_wu_ocr_region_confidence"),
            sa.CheckConstraint("x >= 0 AND y >= 0 AND width > 0 AND height > 0 AND x + width <= 1 AND y + height <= 1", name="ck_wu_ocr_region_bounds"),
            sa.ForeignKeyConstraint(["attempt_id"], ["wu_ocr_page_attempts.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("attempt_id", "region_index", name="uq_wu_ocr_region_order"),
        )
    _ensure_indexes("wu_ocr_regions", (("ix_wu_ocr_regions_attempt_id", ["attempt_id"]),))


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("wu_ocr_regions"):
        op.drop_table("wu_ocr_regions")
    if sa.inspect(bind).has_table("wu_ocr_page_attempts"):
        op.drop_table("wu_ocr_page_attempts")
