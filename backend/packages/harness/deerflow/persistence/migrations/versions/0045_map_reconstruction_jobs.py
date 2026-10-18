"""Persist direct SSH reconstruction jobs without a GPU scheduling queue."""

import sqlalchemy as sa
from alembic import op

revision = "0045_map_reconstruction_jobs"
down_revision = "0044_agent_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_reconstruction_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("point_id", sa.String(255)),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_json", sa.Text(), nullable=False),
    )
    op.create_index("uq_map_reconstruction_request", "map_reconstruction_jobs", ["owner_id", "request_key"], unique=True)
    op.create_index("ix_map_reconstruction_point", "map_reconstruction_jobs", ["point_id", "created_at"])


def downgrade() -> None:
    op.drop_table("map_reconstruction_jobs")
