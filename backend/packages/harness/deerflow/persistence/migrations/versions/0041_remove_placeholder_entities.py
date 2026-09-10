"""Remove non-historical placeholder people from the knowledge graph.

Revision ID: 0041_remove_placeholder_entities
Revises: 0040_poetry_mention_relation
"""

from __future__ import annotations

from alembic import op

revision = "0041_remove_placeholder_entities"
down_revision = "0040_poetry_mention_relation"
branch_labels = None
depends_on = None

_PLACEHOLDER_NAMES = "'张三','李四','王五','赵六'"


def upgrade() -> None:
    op.execute(
        f"""
        DELETE FROM wu_relation_evidence
        WHERE relation_id IN (
            SELECT r.id
            FROM wu_relations r
            JOIN wu_entities e ON e.id IN (r.subject_id, r.object_id)
            WHERE e.canonical_name IN ({_PLACEHOLDER_NAMES})
        )
        """
    )
    op.execute(
        f"""
        DELETE FROM wu_relations
        WHERE subject_id IN (SELECT id FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES}))
           OR object_id IN (SELECT id FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES}))
        """
    )
    op.execute(
        f"""
        DELETE FROM wu_entity_evidence
        WHERE entity_id IN (SELECT id FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES}))
        """
    )
    op.execute(
        f"""
        DELETE FROM wu_event_participants
        WHERE entity_id IN (SELECT id FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES}))
        """
    )
    op.execute(
        f"""
        DELETE FROM wu_geo_evidence
        WHERE entity_id IN (SELECT id FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES}))
        """
    )
    op.execute(
        f"""
        DELETE FROM wu_geo_features
        WHERE entity_id IN (SELECT id FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES}))
        """
    )
    op.execute(
        f"""
        UPDATE wu_historical_events
        SET place_entity_id = NULL
        WHERE place_entity_id IN (SELECT id FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES}))
        """
    )
    op.execute(
        f"""
        DELETE FROM wu_alias_index
        WHERE entity_id IN (SELECT id FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES}))
        """
    )
    op.execute(
        f"DELETE FROM wu_entities WHERE canonical_name IN ({_PLACEHOLDER_NAMES})"
    )


def downgrade() -> None:
    # Placeholder entities are intentionally not recreated on downgrade.
    pass
