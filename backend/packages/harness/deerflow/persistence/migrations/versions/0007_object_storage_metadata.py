"""Object storage metadata without object bytes.

Revision ID: 0007_object_storage_metadata
Revises: 0006_wu_culture_persistence
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_object_storage_metadata"
down_revision: str | Sequence[str] | None = "0006_wu_culture_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wu_object_metadata"):
        op.create_table(
            "wu_object_metadata",
            sa.Column("object_key", sa.Text(), nullable=False),
            sa.Column("owner_id", sa.String(length=255), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("mime_type", sa.String(length=255), nullable=False),
            sa.Column("size", sa.BigInteger(), nullable=False),
            sa.Column("backend", sa.String(length=32), nullable=False),
            sa.Column("storage_uri", sa.Text(), nullable=False),
            sa.Column("original_filename", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("object_key"),
        )
    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("wu_object_metadata")}
    if "ix_wu_object_metadata_owner_id" not in existing_indexes:
        op.create_index("ix_wu_object_metadata_owner_id", "wu_object_metadata", ["owner_id"], unique=False)
    if "ix_wu_object_metadata_owner_sha256" not in existing_indexes:
        op.create_index("ix_wu_object_metadata_owner_sha256", "wu_object_metadata", ["owner_id", "sha256"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_wu_object_metadata_owner_sha256", table_name="wu_object_metadata")
    op.drop_index("ix_wu_object_metadata_owner_id", table_name="wu_object_metadata")
    op.drop_table("wu_object_metadata")

