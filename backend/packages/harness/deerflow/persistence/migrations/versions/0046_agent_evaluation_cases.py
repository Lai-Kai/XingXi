"""Persist automatic evaluation questions independently of manual evaluations.

Revision ID: 0046_agent_evaluation_cases
Revises: 0045_evidence_lookup_index
"""

import sqlalchemy as sa
from alembic import op

revision = "0046_agent_evaluation_cases"
down_revision = "0045_evidence_lookup_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("wu_agent_evaluation_cases"):
        op.create_table(
            "wu_agent_evaluation_cases",
            sa.Column("case_id", sa.String(128), primary_key=True),
            sa.Column("case_json", sa.Text()),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_by", sa.String(255), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("wu_agent_evaluation_cases")
