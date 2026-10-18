"""Index exact Chunk/document Evidence joins used by graph discovery.

Revision ID: 0045_evidence_lookup_index
Revises: 0044_agent_evaluations
"""

import sqlalchemy as sa
from alembic import op

revision = "0045_evidence_lookup_index"
down_revision = "0044_agent_evaluations"
branch_labels = None
depends_on = None

_INDEX = "ix_wu_evidence_chunk_document"


def upgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("wu_evidence")}
    if _INDEX not in indexes:
        op.create_index(_INDEX, "wu_evidence", ["chunk_id", "document_id"])


def downgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("wu_evidence")}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name="wu_evidence")
