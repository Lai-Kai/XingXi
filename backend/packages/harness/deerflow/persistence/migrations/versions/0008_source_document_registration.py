"""Source document registration metadata and audit fields.

Revision ID: 0008_source_registration
Revises: 0007_object_storage_metadata
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_source_registration"
down_revision: str | Sequence[str] | None = "0007_object_storage_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "wu_source_documents"


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}


def _indexes() -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    additions = [
        sa.Column("source_institution", sa.Text(), nullable=True),
        sa.Column("holder", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]
    with op.batch_alter_table(_TABLE) as batch:
        for column in additions:
            if column.name not in columns:
                batch.add_column(column)

    op.execute(sa.text("UPDATE wu_source_documents SET source_institution = COALESCE(source_institution, 'unknown'), holder = COALESCE(holder, 'unknown'), status = COALESCE(status, 'registered')"))
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column("source_institution", existing_type=sa.Text(), nullable=False)
        batch.alter_column("holder", existing_type=sa.Text(), nullable=False)
        batch.alter_column("status", existing_type=sa.String(length=32), nullable=False)

    indexes = _indexes()
    if "ix_wu_source_documents_status" not in indexes:
        op.create_index("ix_wu_source_documents_status", _TABLE, ["status"], unique=False)
    if "ix_wu_source_documents_created_by" not in indexes:
        op.create_index("ix_wu_source_documents_created_by", _TABLE, ["created_by"], unique=False)


def downgrade() -> None:
    indexes = _indexes()
    if "ix_wu_source_documents_created_by" in indexes:
        op.drop_index("ix_wu_source_documents_created_by", table_name=_TABLE)
    if "ix_wu_source_documents_status" in indexes:
        op.drop_index("ix_wu_source_documents_status", table_name=_TABLE)
    columns = _columns()
    with op.batch_alter_table(_TABLE) as batch:
        for name in (
            "updated_at",
            "updated_by",
            "created_at",
            "created_by",
            "status",
            "holder",
            "source_institution",
        ):
            if name in columns:
                batch.drop_column(name)
