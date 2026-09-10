"""Add public/internal scope to knowledge releases.

Revision ID: 0034_internal_working_releases
Revises: 0033_fuxianzhi_corpus_import
"""

from alembic import op
import sqlalchemy as sa

revision = "0034_internal_working_releases"
down_revision = "0033_fuxianzhi_corpus_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("wu_knowledge_releases") as batch:
        batch.add_column(sa.Column("scope", sa.String(length=20), nullable=False, server_default="public"))


def downgrade() -> None:
    with op.batch_alter_table("wu_knowledge_releases") as batch:
        batch.drop_column("scope")
