"""Persist historical events and geospatial features.

Revision ID: 0030_events_geo
Revises: 0029_knowledge_graph_relations
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_events_geo"
down_revision = "0029_knowledge_graph_relations"
branch_labels = None
depends_on = None


def _index(name: str, table: str, columns: list[str]) -> None:
    if name not in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wu_historical_events"):
        op.create_table(
            "wu_historical_events",
            sa.Column("id", sa.String(255), primary_key=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("start_time", sa.String(128), nullable=True),
            sa.Column("end_time", sa.String(128), nullable=True),
            sa.Column("time_certainty", sa.String(20), nullable=False),
            sa.Column("place_entity_id", sa.String(255), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("is_inferred", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("review_status", sa.String(20), nullable=False),
            sa.Column("release_id", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["place_entity_id"], ["wu_entities.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="SET NULL"),
            sa.CheckConstraint("time_certainty IN ('exact','approximate','unknown')", name="ck_wu_events_time_certainty"),
            sa.CheckConstraint("review_status IN ('pending','reviewed','disputed','rejected')", name="ck_wu_events_review_status"),
        )
        for name, columns in (
            ("ix_wu_events_title", ["title"]),
            ("ix_wu_events_type", ["event_type"]),
            ("ix_wu_events_start_time", ["start_time"]),
            ("ix_wu_events_place", ["place_entity_id"]),
            ("ix_wu_events_review", ["review_status"]),
            ("ix_wu_events_release", ["release_id"]),
        ):
            _index(name, "wu_historical_events", columns)
    if not inspector.has_table("wu_event_participants"):
        op.create_table(
            "wu_event_participants",
            sa.Column("event_id", sa.String(255), primary_key=True),
            sa.Column("entity_id", sa.String(255), primary_key=True),
            sa.ForeignKeyConstraint(["event_id"], ["wu_historical_events.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["entity_id"], ["wu_entities.id"], ondelete="RESTRICT"),
        )
        _index("ix_wu_event_participants_entity", "wu_event_participants", ["entity_id"])
    if not inspector.has_table("wu_event_evidence"):
        op.create_table(
            "wu_event_evidence",
            sa.Column("event_id", sa.String(255), primary_key=True),
            sa.Column("evidence_id", sa.String(255), primary_key=True),
            sa.ForeignKeyConstraint(["event_id"], ["wu_historical_events.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["evidence_id"], ["wu_evidence.id"], ondelete="RESTRICT"),
        )
        _index("ix_wu_event_evidence_evidence", "wu_event_evidence", ["evidence_id"])
    if not inspector.has_table("wu_geo_features"):
        op.create_table(
            "wu_geo_features",
            sa.Column("entity_id", sa.String(255), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("confidence", sa.String(20), nullable=False),
            sa.Column("basis", sa.Text(), nullable=False),
            sa.Column("review_status", sa.String(20), nullable=False),
            sa.Column("release_id", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["entity_id"], ["wu_entities.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="SET NULL"),
            sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_wu_geo_longitude"),
            sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_wu_geo_latitude"),
            sa.CheckConstraint("confidence IN ('exact','approximate','speculative')", name="ck_wu_geo_confidence"),
            sa.CheckConstraint("review_status IN ('pending','reviewed','disputed','rejected')", name="ck_wu_geo_review_status"),
        )
        for name, columns in (
            ("ix_wu_geo_name", ["name"]),
            ("ix_wu_geo_confidence", ["confidence"]),
            ("ix_wu_geo_review", ["review_status"]),
            ("ix_wu_geo_release", ["release_id"]),
        ):
            _index(name, "wu_geo_features", columns)
    if not inspector.has_table("wu_geo_evidence"):
        op.create_table(
            "wu_geo_evidence",
            sa.Column("entity_id", sa.String(255), primary_key=True),
            sa.Column("evidence_id", sa.String(255), primary_key=True),
            sa.ForeignKeyConstraint(["entity_id"], ["wu_geo_features.entity_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["evidence_id"], ["wu_evidence.id"], ondelete="RESTRICT"),
        )
        _index("ix_wu_geo_evidence_evidence", "wu_geo_evidence", ["evidence_id"])


def downgrade() -> None:
    for table in (
        "wu_geo_evidence",
        "wu_geo_features",
        "wu_event_evidence",
        "wu_event_participants",
        "wu_historical_events",
    ):
        if sa.inspect(op.get_bind()).has_table(table):
            op.drop_table(table)
