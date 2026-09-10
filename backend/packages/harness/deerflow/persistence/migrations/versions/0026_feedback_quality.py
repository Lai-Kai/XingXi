"""Add persistent quality workflow fields to feedback.

Revision ID: 0026_feedback_quality
Revises: 0025_business_roles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_feedback_quality"
down_revision = "0025_business_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("feedback")}
    if "category" not in columns:
        op.add_column("feedback", sa.Column("category", sa.String(32), nullable=True))
        op.create_index("ix_feedback_category", "feedback", ["category"])
    if "status" not in columns:
        op.add_column("feedback", sa.Column("status", sa.String(32), nullable=False, server_default="submitted"))
        op.create_index("ix_feedback_status", "feedback", ["status"])
    if "assignee_id" not in columns:
        op.add_column("feedback", sa.Column("assignee_id", sa.String(64), nullable=True))
        op.create_index("ix_feedback_assignee_id", "feedback", ["assignee_id"])
    if "review_note" not in columns:
        op.add_column("feedback", sa.Column("review_note", sa.Text(), nullable=True))
    if "updated_at" not in columns:
        op.add_column("feedback", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        op.execute("UPDATE feedback SET updated_at = created_at WHERE updated_at IS NULL")


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("feedback")}
    for index_name, column_name in (
        ("ix_feedback_assignee_id", "assignee_id"),
        ("ix_feedback_status", "status"),
        ("ix_feedback_category", "category"),
    ):
        if column_name in columns:
            op.drop_index(index_name, table_name="feedback")
    for name in ("updated_at", "review_note", "assignee_id", "status", "category"):
        if name in columns:
            op.drop_column("feedback", name)
