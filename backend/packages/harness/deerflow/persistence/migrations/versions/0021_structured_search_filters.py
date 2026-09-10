"""Add normalized structured-search filter metadata and facets.

Revision ID: 0021_structured_search_filters
Revises: 0020_vector_search
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_structured_search_filters"
down_revision: str | Sequence[str] | None = "0020_vector_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("wu_search_filter_metadata"):
        op.create_table(
            "wu_search_filter_metadata",
            sa.Column("release_id", sa.String(length=255), primary_key=True),
            sa.Column("chunk_id", sa.String(length=255), primary_key=True),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("edition", sa.Text(), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_level", sa.String(length=1), nullable=False),
            sa.Column("review_status", sa.String(length=20), nullable=False),
            sa.Column("spatial_confidence", sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["chunk_id"], ["wu_text_chunks.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.CheckConstraint("review_status IN ('pending', 'reviewed', 'disputed', 'rejected')", name="ck_wu_search_filter_review_status"),
            sa.CheckConstraint("spatial_confidence IS NULL OR (spatial_confidence >= 0 AND spatial_confidence <= 1)", name="ck_wu_search_filter_spatial_confidence"),
        )
    _ensure_indexes(
        "wu_search_filter_metadata",
        tuple((f"ix_wu_search_filter_metadata_{column}", [column]) for column in ("document_id", "edition", "source_type", "source_level", "review_status", "spatial_confidence")),
    )

    if not sa.inspect(op.get_bind()).has_table("wu_search_filter_facets"):
        op.create_table(
            "wu_search_filter_facets",
            sa.Column("release_id", sa.String(length=255), primary_key=True),
            sa.Column("chunk_id", sa.String(length=255), primary_key=True),
            sa.Column("facet_type", sa.String(length=20), primary_key=True),
            sa.Column("facet_value", sa.String(length=64), primary_key=True),
            sa.ForeignKeyConstraint(
                ["release_id", "chunk_id"],
                ["wu_search_filter_metadata.release_id", "wu_search_filter_metadata.chunk_id"],
                ondelete="CASCADE",
            ),
            sa.CheckConstraint("facet_type IN ('dynasty', 'entity_type')", name="ck_wu_search_filter_facet_type"),
        )
    _ensure_indexes(
        "wu_search_filter_facets",
        (("ix_wu_search_filter_facet_lookup", ["facet_type", "facet_value", "release_id", "chunk_id"]),),
    )

    bind = op.get_bind()
    if sa.inspect(bind).has_table("wu_fulltext_documents"):
        bind.execute(
            sa.text(
                "INSERT INTO wu_search_filter_metadata "
                "(release_id, chunk_id, document_id, edition, source_type, source_level, review_status, spatial_confidence) "
                "SELECT d.release_id, d.chunk_id, d.document_id, d.edition, d.source_type, d.source_level, 'reviewed', NULL "
                "FROM wu_fulltext_documents d "
                "WHERE NOT EXISTS (SELECT 1 FROM wu_search_filter_metadata m "
                "WHERE m.release_id = d.release_id AND m.chunk_id = d.chunk_id)"
            )
        )


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    op.drop_table("wu_search_filter_facets")
    op.drop_table("wu_search_filter_metadata")
