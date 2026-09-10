"""Add Xingxi business role profiles to users.

Revision ID: 0025_business_roles
Revises: 0024_research_projects
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_business_roles"
down_revision = "0024_research_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "business_role" not in columns:
        op.add_column(
            "users",
            sa.Column("business_role", sa.String(32), nullable=False, server_default="public"),
        )
    if "organization_name" not in columns:
        op.add_column("users", sa.Column("organization_name", sa.String(255), nullable=True))

    op.execute("UPDATE users SET business_role = 'government' WHERE system_role = 'admin' AND business_role = 'public'")


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "organization_name" in columns:
        op.drop_column("users", "organization_name")
    if "business_role" in columns:
        op.drop_column("users", "business_role")
