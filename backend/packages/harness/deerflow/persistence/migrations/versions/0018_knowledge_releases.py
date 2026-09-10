"""Add immutable knowledge releases and atomic active-version state.

Revision ID: 0018_knowledge_releases
Revises: 0017_text_review
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_knowledge_releases"
down_revision: str | Sequence[str] | None = "0017_text_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wu_knowledge_releases"):
        op.create_table(
            "wu_knowledge_releases",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("release_notes", sa.Text(), nullable=False),
            sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("version_number", name="uq_wu_knowledge_release_version"),
            sa.UniqueConstraint("manifest_sha256", name="uq_wu_knowledge_release_manifest"),
            sa.CheckConstraint("version_number >= 1", name="ck_wu_knowledge_release_version"),
        )
    _ensure_indexes(
        "wu_knowledge_releases",
        (
            ("ix_wu_knowledge_releases_version_number", ["version_number"]),
            ("ix_wu_knowledge_releases_manifest_sha256", ["manifest_sha256"]),
            ("ix_wu_knowledge_releases_created_by", ["created_by"]),
            ("ix_wu_knowledge_releases_created_at", ["created_at"]),
        ),
    )

    if not sa.inspect(op.get_bind()).has_table("wu_knowledge_release_items"):
        op.create_table(
            "wu_knowledge_release_items",
            sa.Column("release_id", sa.String(length=255), primary_key=True),
            sa.Column("ordinal", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("chunk_set_id", sa.String(length=255), nullable=False),
            sa.Column("chunk_id", sa.String(length=255), nullable=False),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("cleaned_page_ids_json", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["chunk_set_id"], ["wu_chunk_sets.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["chunk_id"], ["wu_text_chunks.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("release_id", "chunk_id", name="uq_wu_knowledge_release_chunk"),
            sa.CheckConstraint("ordinal >= 0", name="ck_wu_knowledge_release_item_ordinal"),
        )
    _ensure_indexes(
        "wu_knowledge_release_items",
        tuple((f"ix_wu_knowledge_release_items_{column}", [column]) for column in ("document_id", "source_file_id", "chunk_set_id", "chunk_id")),
    )

    if not sa.inspect(op.get_bind()).has_table("wu_knowledge_release_state"):
        op.create_table(
            "wu_knowledge_release_state",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("active_release_id", sa.String(length=255), nullable=True),
            sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_by", sa.String(length=255), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["active_release_id"], ["wu_knowledge_releases.id"], ondelete="RESTRICT"),
            sa.CheckConstraint("state_version >= 0", name="ck_wu_knowledge_release_state_version"),
        )
    _ensure_indexes(
        "wu_knowledge_release_state",
        (
            ("ix_wu_knowledge_release_state_active_release_id", ["active_release_id"]),
            ("ix_wu_knowledge_release_state_updated_by", ["updated_by"]),
        ),
    )
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT id FROM wu_knowledge_release_state WHERE id = 'active'")).first() is None:
        bind.execute(sa.text("INSERT INTO wu_knowledge_release_state (id, active_release_id, state_version) VALUES ('active', NULL, 0)"))

    if not sa.inspect(op.get_bind()).has_table("wu_knowledge_release_events"):
        op.create_table(
            "wu_knowledge_release_events",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("action", sa.String(length=20), nullable=False),
            sa.Column("previous_release_id", sa.String(length=255), nullable=True),
            sa.Column("new_release_id", sa.String(length=255), nullable=False),
            sa.Column("state_version", sa.Integer(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("actor_id", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["previous_release_id"], ["wu_knowledge_releases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["new_release_id"], ["wu_knowledge_releases.id"], ondelete="RESTRICT"),
            sa.CheckConstraint("state_version >= 1", name="ck_wu_knowledge_release_event_state_version"),
            sa.CheckConstraint("action IN ('publish', 'activate', 'rollback')", name="ck_wu_knowledge_release_event_action"),
        )
    _ensure_indexes(
        "wu_knowledge_release_events",
        tuple((f"ix_wu_knowledge_release_events_{column}", [column]) for column in ("action", "new_release_id", "state_version", "actor_id", "created_at")),
    )


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    op.drop_table("wu_knowledge_release_events")
    op.drop_table("wu_knowledge_release_state")
    op.drop_table("wu_knowledge_release_items")
    op.drop_table("wu_knowledge_releases")
