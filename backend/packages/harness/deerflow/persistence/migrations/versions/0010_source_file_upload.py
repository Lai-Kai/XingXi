"""Bind uploaded source files to stored objects.

Revision ID: 0010_source_file_upload
Revises: 0009_source_authorization
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_source_file_upload"
down_revision: str | Sequence[str] | None = "0009_source_authorization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "wu_source_files"


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("object_key", sa.Text(), nullable=False),
            sa.Column("original_filename", sa.Text(), nullable=False),
            sa.Column("mime_type", sa.String(length=255), nullable=False),
            sa.Column("size", sa.BigInteger(), nullable=False),
            sa.Column("uploaded_by", sa.String(length=255), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["object_key"], ["wu_object_metadata.object_key"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(_TABLE)}
    for name, columns in (
        ("ix_wu_source_files_document_id", ["document_id"]),
        ("ix_wu_source_files_object_key", ["object_key"]),
        ("ix_wu_source_files_uploaded_by", ["uploaded_by"]),
        ("ix_wu_source_files_uploaded_at", ["uploaded_at"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, _TABLE, columns, unique=False)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
