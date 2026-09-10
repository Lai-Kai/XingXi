"""Add the Xingxi operations and continuous-improvement loop.

Revision ID: 0028_operations_loop
Revises: 0027_extensible_source_types
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_operations_loop"
down_revision = "0027_extensible_source_types"
branch_labels = None
depends_on = None


def _create_indexes(table: str, definitions: tuple[tuple[str, list[str]], ...]) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table, columns)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wu_operation_events"):
        op.create_table(
            "wu_operation_events",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("event_type", sa.String(32), nullable=False),
            sa.Column("event_key", sa.String(255), nullable=True),
            sa.Column("user_id", sa.String(64), nullable=True),
            sa.Column("thread_id", sa.String(64), nullable=True),
            sa.Column("run_id", sa.String(64), nullable=True),
            sa.Column("release_id", sa.String(255), nullable=True),
            sa.Column("entity_id", sa.String(255), nullable=True),
            sa.Column("entity_name", sa.String(255), nullable=True),
            sa.Column("citation_count", sa.Integer(), nullable=True),
            sa.Column("is_accurate", sa.Boolean(), nullable=True),
            sa.Column("refused", sa.Boolean(), nullable=True),
            sa.Column("refusal_compliant", sa.Boolean(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("citation_count IS NULL OR citation_count >= 0", name="ck_wu_operation_event_citations"),
        )
    _create_indexes("wu_operation_events", (("ix_wu_operation_events_type_time", ["event_type", "occurred_at"]), ("ix_wu_operation_events_entity", ["entity_id"]), ("ix_wu_operation_events_release", ["release_id"])))
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("wu_operation_events")}
    if "uq_wu_operation_events_key" not in existing:
        op.create_index("uq_wu_operation_events_key", "wu_operation_events", ["event_key"], unique=True)

    if not inspector.has_table("wu_correction_records"):
        op.create_table(
            "wu_correction_records",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("target_type", sa.String(32), nullable=False),
            sa.Column("target_id", sa.String(255), nullable=False),
            sa.Column("release_id", sa.String(255), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("before_json", sa.Text(), nullable=False),
            sa.Column("after_json", sa.Text(), nullable=False),
            sa.Column("actor_id", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_indexes("wu_correction_records", (("ix_wu_correction_target", ["target_type", "target_id"]), ("ix_wu_correction_created", ["created_at"]), ("ix_wu_correction_release", ["release_id"])))

    if not inspector.has_table("wu_evaluation_cases"):
        op.create_table(
            "wu_evaluation_cases",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("expected_status", sa.String(16), nullable=False),
            sa.Column("min_citations", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("required_terms_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("expected_status IN ('answered','refused')", name="ck_wu_evaluation_case_status"),
            sa.CheckConstraint("min_citations >= 0", name="ck_wu_evaluation_case_citations"),
        )
    _create_indexes("wu_evaluation_cases", (("ix_wu_evaluation_cases_active", ["active"]), ("ix_wu_evaluation_cases_created", ["created_at"])))

    if not inspector.has_table("wu_evaluation_runs"):
        op.create_table(
            "wu_evaluation_runs",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("release_id", sa.String(255), nullable=True),
            sa.Column("asset_version_id", sa.String(64), nullable=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("total", sa.Integer(), nullable=False),
            sa.Column("passed", sa.Integer(), nullable=False),
            sa.Column("pass_rate", sa.Float(), nullable=True),
            sa.Column("created_by", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_indexes("wu_evaluation_runs", (("ix_wu_evaluation_runs_created", ["created_at"]), ("ix_wu_evaluation_runs_release", ["release_id"])))

    if not inspector.has_table("wu_evaluation_results"):
        op.create_table(
            "wu_evaluation_results",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("run_id", sa.String(64), nullable=False),
            sa.Column("case_id", sa.String(64), nullable=False),
            sa.Column("actual_status", sa.String(16), nullable=False),
            sa.Column("citation_count", sa.Integer(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("passed", sa.Boolean(), nullable=False),
            sa.Column("failure_reasons_json", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["wu_evaluation_runs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["case_id"], ["wu_evaluation_cases.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("run_id", "case_id", name="uq_wu_evaluation_result_case"),
        )
    _create_indexes("wu_evaluation_results", (("ix_wu_evaluation_results_run", ["run_id"]), ("ix_wu_evaluation_results_case", ["case_id"])))

    if not inspector.has_table("wu_asset_versions"):
        op.create_table(
            "wu_asset_versions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("knowledge_release_id", sa.String(255), nullable=False),
            sa.Column("knowledge_release_version", sa.String(32), nullable=False),
            sa.Column("graph_manifest_sha256", sa.String(64), nullable=False),
            sa.Column("map_manifest_sha256", sa.String(64), nullable=False),
            sa.Column("entity_count", sa.Integer(), nullable=False),
            sa.Column("map_point_count", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("knowledge_release_id", name="uq_wu_asset_version_release"),
        )
    _create_indexes("wu_asset_versions", (("ix_wu_asset_versions_created", ["created_at"]), ("ix_wu_asset_versions_release", ["knowledge_release_id"])))


def downgrade() -> None:
    for table in ("wu_asset_versions", "wu_evaluation_results", "wu_evaluation_runs", "wu_evaluation_cases", "wu_correction_records", "wu_operation_events"):
        if sa.inspect(op.get_bind()).has_table(table):
            op.drop_table(table)
