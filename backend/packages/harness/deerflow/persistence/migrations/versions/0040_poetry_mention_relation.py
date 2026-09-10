"""Add an explicit relation for places mentioned by a poem.

Revision ID: 0040_poetry_mention_relation
Revises: 0039_relation_vocabulary
"""

from __future__ import annotations

from alembic import op

revision = "0040_poetry_mention_relation"
down_revision = "0039_relation_vocabulary"
branch_labels = None
depends_on = None

_RELATION_TYPES = (
    "'located_in','built_by','repaired_in','crosses','related_to',"
    "'sibling_of','spouse_of','parent_of','lived_in','visited',"
    "'born_in','worked_at','studied_at','died_at','composed_at',"
    "'mentioned_in_poetry','documented_in'"
)


def upgrade() -> None:
    with op.batch_alter_table("wu_relations") as batch_op:
        batch_op.drop_constraint("ck_wu_relations_type", type_="check")
        batch_op.create_check_constraint(
            "ck_wu_relations_type",
            f"relation_type IN ({_RELATION_TYPES})",
        )


def downgrade() -> None:
    op.execute("DELETE FROM wu_relations WHERE relation_type = 'mentioned_in_poetry'")
    with op.batch_alter_table("wu_relations") as batch_op:
        batch_op.drop_constraint("ck_wu_relations_type", type_="check")
        batch_op.create_check_constraint(
            "ck_wu_relations_type",
            "relation_type IN ('located_in','built_by','repaired_in','crosses','related_to','sibling_of','spouse_of','parent_of','lived_in','visited','born_in','worked_at','studied_at','died_at','composed_at','documented_in')",
        )
