"""Add stable historical entity tables.

Revision ID: 0023_entities
Revises: 0022_alias_query_expansion
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_entities"
down_revision: str | Sequence[str] | None = "0022_alias_query_expansion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITY_TYPES = (
    "person",
    "family",
    "place",
    "waterway",
    "bridge",
    "building",
    "garden",
    "relic",
    "organization",
    "work",
    "event",
)


def _ensure_indexes(table: str, indexes: tuple[tuple[str, list[str]], ...]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {index["name"] for index in inspector.get_indexes(table)}
    for name, columns in indexes:
        if name not in existing:
            op.create_index(name, table, columns)


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("wu_entities"):
        op.create_table(
            "wu_entities",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("canonical_name", sa.String(length=255), nullable=False),
            sa.Column("entity_type", sa.String(length=32), nullable=False),
            sa.Column("dynasty", sa.String(length=64), nullable=True),
            sa.Column("extant_status", sa.String(length=64), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("review_status", sa.String(length=20), nullable=False),
            sa.Column("release_id", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="SET NULL"),
            sa.CheckConstraint(
                "entity_type IN (" + ", ".join(f"'{item}'" for item in _ENTITY_TYPES) + ")",
                name="ck_wu_entities_type",
            ),
            sa.CheckConstraint(
                "review_status IN ('pending', 'reviewed', 'disputed', 'rejected')",
                name="ck_wu_entities_review_status",
            ),
        )
    _ensure_indexes(
        "wu_entities",
        (
            ("ix_wu_entities_canonical_name", ["canonical_name"]),
            ("ix_wu_entities_entity_type", ["entity_type"]),
            ("ix_wu_entities_review_status", ["review_status"]),
            ("ix_wu_entities_release_id", ["release_id"]),
        ),
    )

    if not sa.inspect(op.get_bind()).has_table("wu_entity_evidence"):
        op.create_table(
            "wu_entity_evidence",
            sa.Column("entity_id", sa.String(length=255), primary_key=True),
            sa.Column("evidence_id", sa.String(length=255), primary_key=True),
            sa.ForeignKeyConstraint(["entity_id"], ["wu_entities.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["evidence_id"], ["wu_evidence.id"], ondelete="RESTRICT"),
        )
    _ensure_indexes("wu_entity_evidence", (("ix_wu_entity_evidence_evidence_id", ["evidence_id"]),))


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("wu_entity_evidence"):
        op.drop_table("wu_entity_evidence")
    if sa.inspect(op.get_bind()).has_table("wu_entities"):
        op.drop_table("wu_entities")
