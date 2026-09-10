"""Source authorization policy and immutable audit events.

Revision ID: 0009_source_authorization
Revises: 0008_source_registration
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_source_authorization"
down_revision: str | Sequence[str] | None = "0008_source_registration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TABLE = "wu_source_documents"
_EVENT_TABLE = "wu_source_authorization_events"


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    source_columns = _columns(_SOURCE_TABLE)
    additions = [
        sa.Column("authorization_status", sa.String(length=32), nullable=True),
        sa.Column("authorization_basis", sa.Text(), nullable=True),
        sa.Column("authorization_valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorization_valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visibility_scope", sa.String(length=32), nullable=True),
        sa.Column("authorized_uses_json", sa.Text(), nullable=True),
        sa.Column("authorization_proof_object_key", sa.Text(), nullable=True),
    ]
    with op.batch_alter_table(_SOURCE_TABLE) as batch:
        for column in additions:
            if column.name not in source_columns:
                batch.add_column(column)

    op.execute(
        sa.text("UPDATE wu_source_documents SET authorization_status = COALESCE(authorization_status, 'unconfirmed'), visibility_scope = COALESCE(visibility_scope, 'internal'), authorized_uses_json = COALESCE(authorized_uses_json, '[]')")
    )
    with op.batch_alter_table(_SOURCE_TABLE) as batch:
        batch.alter_column("authorization_status", existing_type=sa.String(length=32), nullable=False)
        batch.alter_column("visibility_scope", existing_type=sa.String(length=32), nullable=False)
        batch.alter_column("authorized_uses_json", existing_type=sa.Text(), nullable=False)

    source_indexes = _indexes(_SOURCE_TABLE)
    if "ix_wu_source_documents_authorization_status" not in source_indexes:
        op.create_index(
            "ix_wu_source_documents_authorization_status",
            _SOURCE_TABLE,
            ["authorization_status"],
            unique=False,
        )
    if "ix_wu_source_documents_authorization_valid_until" not in source_indexes:
        op.create_index(
            "ix_wu_source_documents_authorization_valid_until",
            _SOURCE_TABLE,
            ["authorization_valid_until"],
            unique=False,
        )

    if not sa.inspect(op.get_bind()).has_table(_EVENT_TABLE):
        op.create_table(
            _EVENT_TABLE,
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("previous_status", sa.String(length=32), nullable=False),
            sa.Column("new_status", sa.String(length=32), nullable=False),
            sa.Column("previous_copyright_status", sa.String(length=32), nullable=False),
            sa.Column("new_copyright_status", sa.String(length=32), nullable=False),
            sa.Column("new_visibility_scope", sa.String(length=32), nullable=False),
            sa.Column("new_authorized_uses_json", sa.Text(), nullable=False),
            sa.Column("authorization_valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("authorization_proof_object_key", sa.Text(), nullable=True),
            sa.Column("changed_by", sa.String(length=255), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    event_indexes = _indexes(_EVENT_TABLE)
    for index_name, columns in (
        ("ix_wu_source_authorization_events_document_id", ["document_id"]),
        ("ix_wu_source_authorization_events_changed_by", ["changed_by"]),
        ("ix_wu_source_authorization_events_changed_at", ["changed_at"]),
    ):
        if index_name not in event_indexes:
            op.create_index(index_name, _EVENT_TABLE, columns, unique=False)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(_EVENT_TABLE):
        op.drop_table(_EVENT_TABLE)
    source_indexes = _indexes(_SOURCE_TABLE)
    for index_name in (
        "ix_wu_source_documents_authorization_valid_until",
        "ix_wu_source_documents_authorization_status",
    ):
        if index_name in source_indexes:
            op.drop_index(index_name, table_name=_SOURCE_TABLE)
    source_columns = _columns(_SOURCE_TABLE)
    with op.batch_alter_table(_SOURCE_TABLE) as batch:
        for name in (
            "authorization_proof_object_key",
            "authorized_uses_json",
            "visibility_scope",
            "authorization_valid_until",
            "authorization_valid_from",
            "authorization_basis",
            "authorization_status",
        ):
            if name in source_columns:
                batch.drop_column(name)
