"""Persist evidence-aware knowledge graph relations.

Revision ID: 0029_knowledge_graph_relations
Revises: 0028_operations_loop
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_knowledge_graph_relations"
down_revision = "0028_operations_loop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wu_relations"):
        op.create_table(
            "wu_relations",
            sa.Column("id", sa.String(255), primary_key=True),
            sa.Column("subject_id", sa.String(255), nullable=False),
            sa.Column("relation_type", sa.String(32), nullable=False),
            sa.Column("object_id", sa.String(255), nullable=False),
            sa.Column("start_time", sa.String(128), nullable=True),
            sa.Column("end_time", sa.String(128), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("is_inferred", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("review_status", sa.String(20), nullable=False),
            sa.Column("release_id", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["subject_id"], ["wu_entities.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["object_id"], ["wu_entities.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["release_id"], ["wu_knowledge_releases.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("subject_id", "relation_type", "object_id", "release_id", name="uq_wu_relation_edge_release"),
            sa.CheckConstraint(
                "relation_type IN ('located_in','built_by','repaired_in','crosses','related_to')",
                name="ck_wu_relations_type",
            ),
            sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_wu_relations_confidence"),
            sa.CheckConstraint(
                "review_status IN ('pending', 'reviewed', 'disputed', 'rejected')",
                name="ck_wu_relations_review_status",
            ),
            sa.CheckConstraint("subject_id <> object_id", name="ck_wu_relations_distinct_endpoints"),
        )
        op.create_index("ix_wu_relations_subject_id", "wu_relations", ["subject_id"])
        op.create_index("ix_wu_relations_object_id", "wu_relations", ["object_id"])
        op.create_index("ix_wu_relations_relation_type", "wu_relations", ["relation_type"])
        op.create_index("ix_wu_relations_review_status", "wu_relations", ["review_status"])
        op.create_index("ix_wu_relations_release_id", "wu_relations", ["release_id"])

    if not inspector.has_table("wu_relation_evidence"):
        op.create_table(
            "wu_relation_evidence",
            sa.Column("relation_id", sa.String(255), primary_key=True),
            sa.Column("evidence_id", sa.String(255), primary_key=True),
            sa.ForeignKeyConstraint(["relation_id"], ["wu_relations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["evidence_id"], ["wu_evidence.id"], ondelete="RESTRICT"),
        )
        op.create_index("ix_wu_relation_evidence_evidence_id", "wu_relation_evidence", ["evidence_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("wu_relation_evidence"):
        op.drop_table("wu_relation_evidence")
    if inspector.has_table("wu_relations"):
        op.drop_table("wu_relations")
