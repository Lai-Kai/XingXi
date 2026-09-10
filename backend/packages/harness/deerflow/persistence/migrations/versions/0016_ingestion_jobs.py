"""Add persistent ingestion jobs, steps and progress events.

Revision ID: 0016_ingestion_jobs
Revises: 0015_structured_chunking
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_ingestion_jobs"
down_revision: str | Sequence[str] | None = "0015_structured_chunking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("wu_ingestion_jobs"):
        op.create_table(
            "wu_ingestion_jobs",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("document_id", sa.String(length=255), nullable=False),
            sa.Column("source_file_id", sa.String(length=255), nullable=False),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("current_step", sa.String(length=32), nullable=True),
            sa.Column("progress_percent", sa.Integer(), nullable=False),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("owner_worker_id", sa.String(length=255), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("event_sequence", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["wu_source_documents.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["source_file_id"], ["wu_source_files.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("created_by", "idempotency_key", name="uq_wu_ingestion_job_actor_idempotency"),
            sa.CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_wu_ingestion_job_progress"),
            sa.CheckConstraint("version >= 1", name="ck_wu_ingestion_job_version"),
            sa.CheckConstraint("event_sequence >= 1", name="ck_wu_ingestion_job_event_sequence"),
        )
    if not inspector.has_table("wu_ingestion_steps"):
        op.create_table(
            "wu_ingestion_steps",
            sa.Column("job_id", sa.String(length=255), primary_key=True),
            sa.Column("name", sa.String(length=32), primary_key=True),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("worker_id", sa.String(length=255), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("output_ref", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("retryable", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.ForeignKeyConstraint(["job_id"], ["wu_ingestion_jobs.id"], ondelete="CASCADE"),
            sa.CheckConstraint("attempt_count >= 0", name="ck_wu_ingestion_step_attempt_count"),
        )
    if not inspector.has_table("wu_ingestion_events"):
        op.create_table(
            "wu_ingestion_events",
            sa.Column("job_id", sa.String(length=255), primary_key=True),
            sa.Column("sequence", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("job_status", sa.String(length=32), nullable=False),
            sa.Column("step_name", sa.String(length=32), nullable=True),
            sa.Column("step_status", sa.String(length=32), nullable=True),
            sa.Column("progress_percent", sa.Integer(), nullable=False),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("actor_id", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["job_id"], ["wu_ingestion_jobs.id"], ondelete="CASCADE"),
            sa.CheckConstraint("sequence >= 1", name="ck_wu_ingestion_event_sequence"),
            sa.CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_wu_ingestion_event_progress"),
        )
    for table_name, definitions in (
        (
            "wu_ingestion_jobs",
            (
                ("ix_wu_ingestion_jobs_document_id", ["document_id"]),
                ("ix_wu_ingestion_jobs_source_file_id", ["source_file_id"]),
                ("ix_wu_ingestion_jobs_created_by", ["created_by"]),
                ("ix_wu_ingestion_jobs_status", ["status"]),
                ("ix_wu_ingestion_jobs_current_step", ["current_step"]),
                ("ix_wu_ingestion_jobs_error_code", ["error_code"]),
                ("ix_wu_ingestion_jobs_owner_worker_id", ["owner_worker_id"]),
                ("ix_wu_ingestion_jobs_lease_expires_at", ["lease_expires_at"]),
                ("ix_wu_ingestion_jobs_created_at", ["created_at"]),
                ("ix_wu_ingestion_jobs_updated_at", ["updated_at"]),
            ),
        ),
        (
            "wu_ingestion_steps",
            (
                ("ix_wu_ingestion_steps_status", ["status"]),
                ("ix_wu_ingestion_steps_worker_id", ["worker_id"]),
                ("ix_wu_ingestion_steps_error_code", ["error_code"]),
            ),
        ),
        (
            "wu_ingestion_events",
            (
                ("ix_wu_ingestion_events_event_type", ["event_type"]),
                ("ix_wu_ingestion_events_job_status", ["job_status"]),
                ("ix_wu_ingestion_events_step_name", ["step_name"]),
                ("ix_wu_ingestion_events_error_code", ["error_code"]),
                ("ix_wu_ingestion_events_actor_id", ["actor_id"]),
                ("ix_wu_ingestion_events_created_at", ["created_at"]),
            ),
        ),
    ):
        _ensure_indexes(table_name, definitions)


def _ensure_indexes(table_name: str, definitions: Sequence[tuple[str, list[str]]]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    for name, columns in definitions:
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    op.drop_table("wu_ingestion_events")
    op.drop_table("wu_ingestion_steps")
    op.drop_table("wu_ingestion_jobs")
