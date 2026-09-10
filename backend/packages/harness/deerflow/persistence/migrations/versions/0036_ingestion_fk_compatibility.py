"""Repair ingestion foreign keys left behind by legacy databases.

Revision ID: 0036_ingestion_fk_compatibility
Revises: 0035_spatial_extents
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0036_ingestion_fk_compatibility"
down_revision = "0035_spatial_extents"
branch_labels = None
depends_on = None

_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}
_CONTRACT: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "wu_ingestion_jobs": (
        ("document_id", "wu_source_documents", "id", "RESTRICT"),
        ("source_file_id", "wu_source_files", "id", "RESTRICT"),
    ),
    "wu_ingestion_steps": (("job_id", "wu_ingestion_jobs", "id", "CASCADE"),),
    "wu_ingestion_events": (("job_id", "wu_ingestion_jobs", "id", "CASCADE"),),
}


def upgrade() -> None:
    for table_name, expected in _CONTRACT.items():
        _repair_foreign_keys(table_name, expected)


def downgrade() -> None:
    # This migration only restores the schema contract that 0016 intended.
    # Downgrading must not deliberately recreate a corrupt legacy constraint.
    pass


def _repair_foreign_keys(
    table_name: str,
    expected: Sequence[tuple[str, str, str, str]],
) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return
    foreign_keys = inspector.get_foreign_keys(table_name)
    if _contract(foreign_keys) == set(expected):
        return

    with op.batch_alter_table(
        table_name,
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        for foreign_key in foreign_keys:
            constrained_column = foreign_key["constrained_columns"][0]
            referred_table = foreign_key["referred_table"]
            name = foreign_key["name"] or _foreign_key_name(
                table_name,
                constrained_column,
                referred_table,
            )
            batch.drop_constraint(name, type_="foreignkey")
        for column, referred_table, referred_column, ondelete in expected:
            batch.create_foreign_key(
                _foreign_key_name(table_name, column, referred_table),
                referred_table,
                [column],
                [referred_column],
                ondelete=ondelete,
            )


def _contract(foreign_keys: list[dict]) -> set[tuple[str, str, str, str]]:
    return {
        (
            item["constrained_columns"][0],
            item["referred_table"],
            item["referred_columns"][0],
            item["options"].get("ondelete", "NO ACTION").upper(),
        )
        for item in foreign_keys
        if len(item["constrained_columns"]) == 1 and len(item["referred_columns"]) == 1
    }


def _foreign_key_name(table_name: str, column: str, referred_table: str) -> str:
    return f"fk_{table_name}_{column}_{referred_table}"
