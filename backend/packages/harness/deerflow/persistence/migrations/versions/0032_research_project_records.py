"""Add durable research records to projects.

Revision ID: 0032_research_project_records
Revises: 0031_relation_vocabulary
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_research_project_records"
down_revision = "0031_relation_vocabulary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wu_project_records"):
        op.create_table(
            "wu_project_records",
            sa.Column("id", sa.String(255), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(255),
                sa.ForeignKey("wu_research_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_by", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "kind IN ('question','note','conclusion')",
                name="ck_wu_project_record_kind",
            ),
        )
        op.create_index(
            "ix_wu_project_records_project_created",
            "wu_project_records",
            ["project_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_wu_project_records_project_created",
        table_name="wu_project_records",
    )
    op.drop_table("wu_project_records")
