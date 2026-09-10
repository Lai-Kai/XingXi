"""Add Release-scoped evidence-bound alias index.

Revision ID: 0022_alias_query_expansion
Revises: 0021_structured_search_filters
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_alias_query_expansion"
down_revision: str | Sequence[str] | None = "0021_structured_search_filters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("wu_alias_index"):
        op.create_table(
            "wu_alias_index",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("release_id", sa.String(length=255), nullable=False),
            sa.Column("entity_id", sa.String(length=255), nullable=False),
            sa.Column("canonical_name", sa.String(length=255), nullable=False),
            sa.Column("entity_type", sa.String(length=32), nullable=False),
            sa.Column("alias", sa.String(length=255), nullable=False),
            sa.Column("normalized_alias", sa.String(length=255), nullable=False),
            sa.Column("alias_length", sa.Integer(), nullable=False),
            sa.Column("alias_type", sa.String(length=32), nullable=False),
            sa.Column("review_status", sa.String(length=20), nullable=False),
            sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("release_id", "entity_id", "normalized_alias", name="uq_wu_alias_release_entity_name"),
            sa.CheckConstraint("alias_type IN ('historical_name', 'colloquial_name', 'character_variant', 'modern_name')", name="ck_wu_alias_type"),
            sa.CheckConstraint("review_status IN ('pending', 'reviewed', 'disputed', 'rejected')", name="ck_wu_alias_review_status"),
            sa.CheckConstraint("alias_length >= 1", name="ck_wu_alias_length"),
        )
    _ensure_indexes(
        "wu_alias_index",
        tuple((f"ix_wu_alias_index_{column}", [column]) for column in ("release_id", "entity_id", "entity_type", "normalized_alias", "review_status", "indexed_at")),
    )

    if not sa.inspect(op.get_bind()).has_table("wu_alias_dynasties"):
        op.create_table(
            "wu_alias_dynasties",
            sa.Column("alias_id", sa.String(length=255), primary_key=True),
            sa.Column("dynasty", sa.String(length=64), primary_key=True),
            sa.ForeignKeyConstraint(["alias_id"], ["wu_alias_index.id"], ondelete="CASCADE"),
        )
    _ensure_indexes("wu_alias_dynasties", (("ix_wu_alias_dynasties_dynasty", ["dynasty"]),))

    if not sa.inspect(op.get_bind()).has_table("wu_alias_evidence"):
        op.create_table(
            "wu_alias_evidence",
            sa.Column("alias_id", sa.String(length=255), primary_key=True),
            sa.Column("evidence_id", sa.String(length=255), primary_key=True),
            sa.ForeignKeyConstraint(["alias_id"], ["wu_alias_index.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["evidence_id"], ["wu_evidence.id"], ondelete="RESTRICT"),
        )
    _ensure_indexes("wu_alias_evidence", (("ix_wu_alias_evidence_evidence_id", ["evidence_id"]),))


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    op.drop_table("wu_alias_evidence")
    op.drop_table("wu_alias_dynasties")
    op.drop_table("wu_alias_index")
