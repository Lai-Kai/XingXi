"""Expand knowledge graph relation vocabulary.

Revision ID: 0031_relation_vocabulary
Revises: 0030_events_geo
"""

from __future__ import annotations

from alembic import op

revision = "0031_relation_vocabulary"
down_revision = "0030_events_geo"
branch_labels = None
depends_on = None

_RELATION_TYPES = (
    "'located_in','built_by','repaired_in','crosses','related_to',"
    "'sibling_of','spouse_of','parent_of','lived_in','visited',"
    "'born_in','worked_at','studied_at'"
)


def upgrade() -> None:
    with op.batch_alter_table("wu_relations") as batch_op:
        batch_op.drop_constraint("ck_wu_relations_type", type_="check")
        batch_op.create_check_constraint(
            "ck_wu_relations_type",
            f"relation_type IN ({_RELATION_TYPES})",
        )


def downgrade() -> None:
    with op.batch_alter_table("wu_relations") as batch_op:
        batch_op.drop_constraint("ck_wu_relations_type", type_="check")
        batch_op.create_check_constraint(
            "ck_wu_relations_type",
            "relation_type IN ('located_in','built_by','repaired_in','crosses','related_to')",
        )
