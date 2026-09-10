"""Add versioned vector semantic-search indexes.

Revision ID: 0020_vector_search
Revises: 0019_fulltext_search
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_vector_search"
down_revision: str | Sequence[str] | None = "0019_fulltext_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        from pgvector.sqlalchemy import Vector

        embedding_type = Vector()
    else:
        embedding_type = sa.LargeBinary()

    if not sa.inspect(op.get_bind()).has_table("wu_vector_index_versions"):
        op.create_table(
            "wu_vector_index_versions",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("release_id", sa.String(length=255), nullable=False),
            sa.Column("release_manifest_sha256", sa.String(length=64), nullable=False),
            sa.Column("embedding_model", sa.String(length=255), nullable=False),
            sa.Column("embedding_version", sa.String(length=128), nullable=False),
            sa.Column("dimensions", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("base_state_version", sa.Integer(), nullable=False),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="CASCADE"),
            sa.CheckConstraint("dimensions >= 1", name="ck_wu_vector_index_dimensions"),
            sa.CheckConstraint("item_count >= 0", name="ck_wu_vector_index_item_count"),
            sa.CheckConstraint("base_state_version >= 0", name="ck_wu_vector_index_base_state_version"),
            sa.CheckConstraint("status IN ('building', 'ready', 'failed')", name="ck_wu_vector_index_status"),
        )
    _ensure_indexes(
        "wu_vector_index_versions",
        tuple((f"ix_wu_vector_index_versions_{column}", [column]) for column in ("release_id", "status", "created_by", "created_at")),
    )

    if not sa.inspect(op.get_bind()).has_table("wu_vector_embeddings"):
        op.create_table(
            "wu_vector_embeddings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("index_version_id", sa.String(length=255), nullable=False),
            sa.Column("release_id", sa.String(length=255), nullable=False),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("chunk_id", sa.String(length=255), nullable=False),
            sa.Column("dimensions", sa.Integer(), nullable=False),
            sa.Column("embedding", embedding_type, nullable=False),
            sa.ForeignKeyConstraint(["index_version_id"], ["wu_vector_index_versions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["chunk_id"], ["wu_text_chunks.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("index_version_id", "chunk_id", name="uq_wu_vector_index_chunk"),
            sa.CheckConstraint("dimensions >= 1", name="ck_wu_vector_embedding_dimensions"),
        )
    _ensure_indexes(
        "wu_vector_embeddings",
        tuple((f"ix_wu_vector_embeddings_{column}", [column]) for column in ("index_version_id", "release_id", "document_id", "source_file_id", "chunk_id")),
    )

    if not sa.inspect(op.get_bind()).has_table("wu_vector_index_states"):
        op.create_table(
            "wu_vector_index_states",
            sa.Column("release_id", sa.String(length=255), primary_key=True),
            sa.Column("active_index_id", sa.String(length=255), nullable=True),
            sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["active_index_id"], ["wu_vector_index_versions.id"], ondelete="RESTRICT"),
            sa.CheckConstraint("state_version >= 0", name="ck_wu_vector_index_state_version"),
        )
    _ensure_indexes("wu_vector_index_states", (("ix_wu_vector_index_states_active_index_id", ["active_index_id"]),))


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        names = op.get_bind().execute(sa.text("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'wu_vector_vec_d%'"))
        for (name,) in names:
            if name.removeprefix("wu_vector_vec_d").isdigit():
                op.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
    op.drop_table("wu_vector_index_states")
    op.drop_table("wu_vector_embeddings")
    op.drop_table("wu_vector_index_versions")
