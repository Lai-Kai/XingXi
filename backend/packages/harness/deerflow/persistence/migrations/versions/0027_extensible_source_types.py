"""Add custom labels for source types outside the standard taxonomy.

Revision ID: 0027_extensible_source_types
Revises: 0026_feedback_quality
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_extensible_source_types"
down_revision = "0026_feedback_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("wu_source_documents")}
    if "source_type_label" not in columns:
        op.add_column("wu_source_documents", sa.Column("source_type_label", sa.String(100), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("wu_source_documents")}
    if "source_type_label" in columns:
        op.drop_column("wu_source_documents", "source_type_label")
