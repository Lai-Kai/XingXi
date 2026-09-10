"""Add user-owned research projects."""

import sqlalchemy as sa
from alembic import op

revision = "0024_research_projects"
down_revision = "0023_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wu_research_projects"):
        op.create_table(
            "wu_research_projects",
            sa.Column("id", sa.String(255), primary_key=True),
            sa.Column("owner_id", sa.String(255), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table("wu_project_documents"):
        op.create_table(
            "wu_project_documents",
            sa.Column("project_id", sa.String(255), sa.ForeignKey("wu_research_projects.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("document_id", sa.String(255), sa.ForeignKey("wu_source_documents.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("added_by", sa.String(255), nullable=False),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_wu_project_documents_document_id", "wu_project_documents", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_wu_project_documents_document_id", table_name="wu_project_documents")
    op.drop_table("wu_project_documents")
    op.drop_table("wu_research_projects")
