"""Persist the complete map payload for each knowledge release.

Revision ID: 0038_map_asset_snapshot_body
Revises: 0037_release_preparation_state

The previous schema stored only ``map_manifest_sha256``. A hash proves that a
payload existed, but cannot make the map API serve the same payload that was
prepared for an active release. The column is nullable for legacy rows because
their original payload was never persisted and cannot be reconstructed by a
schema migration alone. ``/api/operations/asset-versions/reconcile`` or a
release retry is the explicit one-time backfill path for those rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_map_asset_snapshot_body"
down_revision = "0037_release_preparation_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wu_asset_versions"):
        return
    columns = {column["name"] for column in inspector.get_columns("wu_asset_versions")}
    if "map_manifest_json" not in columns:
        op.add_column(
            "wu_asset_versions",
            sa.Column("map_manifest_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("wu_asset_versions"):
        columns = {column["name"] for column in inspector.get_columns("wu_asset_versions")}
        if "map_manifest_json" in columns:
            op.drop_column("wu_asset_versions", "map_manifest_json")
