"""Persist manually selected map points independently of knowledge releases."""

import sqlalchemy as sa
from alembic import op

revision = "0046_custom_map_points"
down_revision = "0045_map_reconstruction_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_custom_points",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("uq_map_custom_point_request", "map_custom_points", ["owner_id", "request_key"], unique=True)


def downgrade() -> None:
    op.drop_table("map_custom_points")
