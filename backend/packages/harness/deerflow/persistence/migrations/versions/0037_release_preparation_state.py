"""Track atomic release preparation and activation state.

Revision ID: 0037_release_preparation_state
Revises: 0036_ingestion_fk_compatibility
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_release_preparation_state"
down_revision = "0036_ingestion_fk_compatibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("wu_knowledge_releases") as batch:
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="preparing",
            )
        )
        batch.add_column(sa.Column("failure_code", sa.String(length=128)))
        batch.add_column(sa.Column("failure_message", sa.Text()))
        batch.add_column(
            sa.Column(
                "preparation_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(sa.Column("ready_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("activated_at", sa.DateTime(timezone=True)))

    complete = (
        "EXISTS (SELECT 1 FROM wu_fulltext_index_states f "
        "WHERE f.release_id = wu_knowledge_releases.id AND f.status = 'ready') "
        "AND EXISTS (SELECT 1 FROM wu_asset_versions a "
        "WHERE a.knowledge_release_id = wu_knowledge_releases.id)"
    )
    op.execute(
        sa.text(
            "UPDATE wu_knowledge_releases SET status='ready', ready_at=created_at "
            f"WHERE {complete}"
        )
    )
    op.execute(
        sa.text(
            "UPDATE wu_knowledge_releases SET status='failed', "
            "failure_code='legacy_assets_incomplete', "
            "failure_message='旧版本缺少完整全文索引或图谱/地图资产快照' "
            "WHERE status='preparing'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE wu_knowledge_releases SET status='active', activated_at=created_at "
            "WHERE id=(SELECT active_release_id FROM wu_knowledge_release_state "
            "WHERE id='active') AND status='ready'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE wu_knowledge_release_state SET active_release_id=NULL, "
            "state_version=state_version+1, updated_at=CURRENT_TIMESTAMP "
            "WHERE id='active' AND active_release_id IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM wu_knowledge_releases r "
            "WHERE r.id=wu_knowledge_release_state.active_release_id "
            "AND r.status='active')"
        )
    )
    with op.batch_alter_table("wu_knowledge_releases") as batch:
        batch.create_check_constraint(
            "ck_wu_knowledge_release_status",
            "status IN ('preparing','ready','failed','active')",
        )
        batch.create_check_constraint(
            "ck_wu_knowledge_release_preparation_attempts",
            "preparation_attempts >= 0",
        )
        batch.create_index("ix_wu_knowledge_releases_status", ["status"])
        batch.create_index("ix_wu_knowledge_releases_failure_code", ["failure_code"])


def downgrade() -> None:
    with op.batch_alter_table("wu_knowledge_releases") as batch:
        batch.drop_index("ix_wu_knowledge_releases_failure_code")
        batch.drop_index("ix_wu_knowledge_releases_status")
        batch.drop_constraint(
            "ck_wu_knowledge_release_preparation_attempts", type_="check"
        )
        batch.drop_constraint("ck_wu_knowledge_release_status", type_="check")
        batch.drop_column("activated_at")
        batch.drop_column("ready_at")
        batch.drop_column("preparation_attempts")
        batch.drop_column("failure_message")
        batch.drop_column("failure_code")
        batch.drop_column("status")
