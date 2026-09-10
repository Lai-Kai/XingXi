"""Represent uncertain historical locations as areas instead of false-precision points.

Revision ID: 0035_spatial_extents
Revises: 0034_internal_working_releases
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_spatial_extents"
down_revision = "0034_internal_working_releases"
branch_labels = None
depends_on = None

_DEFAULT_BASIS = "按空间置信等级生成的可视化包络，不代表历史边界或统计概率。"


def upgrade() -> None:
    with op.batch_alter_table("wu_geo_features") as batch:
        batch.add_column(sa.Column("geometry_type", sa.String(length=24), nullable=False, server_default="point"))
        batch.add_column(sa.Column("uncertainty_radius_m", sa.Float(), nullable=True))
        batch.add_column(sa.Column("area_coordinates_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("extent_source", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("extent_basis", sa.Text(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE wu_geo_features SET "
            "geometry_type = 'uncertainty_radius', "
            "uncertainty_radius_m = CASE confidence "
            "WHEN 'approximate' THEN 750.0 ELSE 2500.0 END, "
            "extent_source = 'confidence_default', extent_basis = :basis "
            "WHERE confidence IN ('approximate', 'speculative')"
        ).bindparams(basis=_DEFAULT_BASIS)
    )
    with op.batch_alter_table("wu_geo_features") as batch:
        batch.create_check_constraint(
            "ck_wu_geo_geometry_type",
            "geometry_type IN ('point','uncertainty_radius','historical_area')",
        )
        batch.create_check_constraint(
            "ck_wu_geo_uncertainty_radius",
            "uncertainty_radius_m IS NULL OR "
            "(uncertainty_radius_m >= 10 AND uncertainty_radius_m <= 100000)",
        )


def downgrade() -> None:
    with op.batch_alter_table("wu_geo_features") as batch:
        batch.drop_constraint("ck_wu_geo_uncertainty_radius", type_="check")
        batch.drop_constraint("ck_wu_geo_geometry_type", type_="check")
        batch.drop_column("extent_basis")
        batch.drop_column("extent_source")
        batch.drop_column("area_coordinates_json")
        batch.drop_column("uncertainty_radius_m")
        batch.drop_column("geometry_type")
