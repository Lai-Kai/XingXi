"""Append relation/event review history without inventing legacy decisions.

Revision ID: 0043_graph_review_history
Revises: 0042_prune_unbacked_graph
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_graph_review_history"
down_revision = "0042_prune_unbacked_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wu_graph_review_records",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("object_type", sa.String(20), nullable=False),
        sa.Column("object_id", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=False),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("reviewer_id", sa.String(255), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("object_type", "object_id", "revision", name="uq_wu_graph_review_revision"),
        sa.CheckConstraint("object_type IN ('relation', 'event')", name="ck_wu_graph_review_object"),
        sa.CheckConstraint("revision >= 1", name="ck_wu_graph_review_revision"),
        sa.CheckConstraint("previous_status IN ('pending','reviewed','disputed','rejected')", name="ck_wu_graph_review_previous"),
        sa.CheckConstraint("new_status IN ('pending','reviewed','disputed','rejected')", name="ck_wu_graph_review_new"),
        sa.CheckConstraint("previous_status <> new_status", name="ck_wu_graph_review_changed"),
    )


def downgrade() -> None:
    op.drop_table("wu_graph_review_records")
