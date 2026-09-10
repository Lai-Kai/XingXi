"""Track source-file duplicates and version relationships.

Revision ID: 0011_file_deduplication
Revises: 0010_source_file_upload
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_file_deduplication"
down_revision: str | Sequence[str] | None = "0010_source_file_upload"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "wu_source_files"
_CANONICAL_INDEX = "uq_wu_source_files_canonical_sha256"


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}


def _indexes() -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(_TABLE)}


def upgrade() -> None:
    existing_columns = _columns()
    with op.batch_alter_table(_TABLE) as batch:
        if "sha256" not in existing_columns:
            batch.add_column(sa.Column("sha256", sa.String(length=64), nullable=True))
        if "duplicate_of_file_id" not in existing_columns:
            batch.add_column(sa.Column("duplicate_of_file_id", sa.String(length=255), nullable=True))
        if "version_of_file_id" not in existing_columns:
            batch.add_column(sa.Column("version_of_file_id", sa.String(length=255), nullable=True))

    op.execute(sa.text("UPDATE wu_source_files SET sha256 = (SELECT wu_object_metadata.sha256 FROM wu_object_metadata WHERE wu_object_metadata.object_key = wu_source_files.object_key) WHERE sha256 IS NULL"))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, sha256 FROM wu_source_files ORDER BY uploaded_at, id")).all()
    canonical_by_hash: dict[str, str] = {}
    for file_id, sha256 in rows:
        canonical_id = canonical_by_hash.setdefault(sha256, file_id)
        if canonical_id != file_id:
            bind.execute(
                sa.text("UPDATE wu_source_files SET duplicate_of_file_id = :canonical WHERE id = :file_id"),
                {"canonical": canonical_id, "file_id": file_id},
            )

    foreign_keys = {foreign_key.get("name") for foreign_key in sa.inspect(bind).get_foreign_keys(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column("sha256", existing_type=sa.String(length=64), nullable=False)
        if "fk_wu_source_files_duplicate_of" not in foreign_keys:
            batch.create_foreign_key(
                "fk_wu_source_files_duplicate_of",
                _TABLE,
                ["duplicate_of_file_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if "fk_wu_source_files_version_of" not in foreign_keys:
            batch.create_foreign_key(
                "fk_wu_source_files_version_of",
                _TABLE,
                ["version_of_file_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    existing_indexes = _indexes()
    for name, columns in (
        ("ix_wu_source_files_sha256", ["sha256"]),
        ("ix_wu_source_files_duplicate_of_file_id", ["duplicate_of_file_id"]),
        ("ix_wu_source_files_version_of_file_id", ["version_of_file_id"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, _TABLE, columns, unique=False)
    if _CANONICAL_INDEX not in existing_indexes:
        op.create_index(
            _CANONICAL_INDEX,
            _TABLE,
            ["sha256"],
            unique=True,
            sqlite_where=sa.text("duplicate_of_file_id IS NULL"),
            postgresql_where=sa.text("duplicate_of_file_id IS NULL"),
        )


def downgrade() -> None:
    existing_indexes = _indexes()
    for name in (
        _CANONICAL_INDEX,
        "ix_wu_source_files_version_of_file_id",
        "ix_wu_source_files_duplicate_of_file_id",
        "ix_wu_source_files_sha256",
    ):
        if name in existing_indexes:
            op.drop_index(name, table_name=_TABLE)
    with op.batch_alter_table(_TABLE) as batch:
        for name in ("version_of_file_id", "duplicate_of_file_id", "sha256"):
            if name in _columns():
                batch.drop_column(name)
