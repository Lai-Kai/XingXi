"""Durable isolated agent evaluations, attempts and append-only reviews.

Revision ID: 0044_agent_evaluations
Revises: 0043_graph_review_history
"""

import sqlalchemy as sa
from alembic import op

revision = "0044_agent_evaluations"
down_revision = "0043_graph_review_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("wu_evaluation_runs")}
    additions = [
        sa.Column("execution_mode", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("request_key", sa.String(128)),
        sa.Column("spec_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("environment_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("parent_id", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.String(64)),
        sa.Column("finished_at", sa.String(64)),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]
    for column in additions:
        if column.name not in columns:
            op.add_column("wu_evaluation_runs", column)
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("wu_evaluation_runs")}
    if "uq_wu_evaluation_request" not in indexes:
        op.create_index("uq_wu_evaluation_request", "wu_evaluation_runs", ["created_by", "request_key"], unique=True)
    if not sa.inspect(op.get_bind()).has_table("wu_evaluation_attempts"):
        op.create_table(
            "wu_evaluation_attempts",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("evaluation_run_id", sa.String(64), sa.ForeignKey("wu_evaluation_runs.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("case_id", sa.String(128), nullable=False),
            sa.Column("case_json", sa.Text(), nullable=False),
            sa.Column("result_json", sa.Text()),
            sa.UniqueConstraint("evaluation_run_id", "case_id", name="uq_wu_evaluation_attempt_case"),
        )
    if not sa.inspect(op.get_bind()).has_table("wu_evaluation_reviews"):
        op.create_table(
            "wu_evaluation_reviews",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("evaluation_run_id", sa.String(64), sa.ForeignKey("wu_evaluation_runs.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("case_id", sa.String(128), nullable=False),
            sa.Column("actor_id", sa.String(255), nullable=False),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not sa.inspect(op.get_bind()).has_table("wu_evaluation_worker"):
        op.create_table(
            "wu_evaluation_worker",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner", sa.String(64)),
            sa.Column("run_id", sa.String(64)),
            sa.Column("lease_until", sa.Float(), nullable=False, server_default="0"),
        )
        op.execute(sa.text("INSERT INTO wu_evaluation_worker (id,lease_until) VALUES (1,0)"))


def downgrade() -> None:
    for table in ("wu_evaluation_worker", "wu_evaluation_reviews", "wu_evaluation_attempts"):
        op.drop_table(table)
    op.drop_index("uq_wu_evaluation_request", table_name="wu_evaluation_runs")
    with op.batch_alter_table("wu_evaluation_runs") as batch:
        for column in ("execution_mode", "request_key", "spec_json", "environment_json", "parent_id", "error_message", "started_at", "finished_at", "cancel_requested"):
            batch.drop_column(column)
