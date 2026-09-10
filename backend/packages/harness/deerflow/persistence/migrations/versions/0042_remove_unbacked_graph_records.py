"""Remove graph records that cannot be traced to local corpus evidence.

Revision ID: 0042_prune_unbacked_graph
Revises: 0041_remove_placeholder_entities
"""

from __future__ import annotations

from alembic import op

revision = "0042_prune_unbacked_graph"
down_revision = "0041_remove_placeholder_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Relations and events without evidence are legacy seed data. Remove them
    # before entities so the RESTRICT foreign keys remain valid. Relations
    # pointing at an unbacked entity are removed as well; otherwise deleting
    # that entity would leave an unsupported graph edge behind.
    op.execute(
        """
        DELETE FROM wu_relation_evidence
        WHERE relation_id IN (
            SELECT r.id
            FROM wu_relations r
            WHERE (
                r.subject_id IN (
                    SELECT e.id
                    FROM wu_entities e
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM wu_entity_evidence ee
                        WHERE ee.entity_id = e.id
                    )
                )
                OR r.object_id IN (
                    SELECT e.id
                    FROM wu_entities e
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM wu_entity_evidence ee
                        WHERE ee.entity_id = e.id
                    )
                )
                OR NOT EXISTS (
                    SELECT 1
                    FROM wu_relation_evidence re
                    WHERE re.relation_id = r.id
                )
            )
            AND EXISTS (
                SELECT 1
                FROM wu_relation_evidence re
                WHERE re.relation_id = r.id
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM wu_relations
        WHERE subject_id IN (
                  SELECT e.id
                  FROM wu_entities e
                  WHERE NOT EXISTS (
                      SELECT 1
                      FROM wu_entity_evidence ee
                      WHERE ee.entity_id = e.id
                  )
              )
           OR object_id IN (
                  SELECT e.id
                  FROM wu_entities e
                  WHERE NOT EXISTS (
                      SELECT 1
                      FROM wu_entity_evidence ee
                      WHERE ee.entity_id = e.id
                  )
              )
           OR NOT EXISTS (
                  SELECT 1
                  FROM wu_relation_evidence re
                  WHERE re.relation_id = wu_relations.id
              )
        """
    )
    op.execute(
        """
        DELETE FROM wu_event_participants
        WHERE event_id IN (
            SELECT e.id
            FROM wu_historical_events e
            WHERE NOT EXISTS (
                SELECT 1
                FROM wu_event_evidence ee
                WHERE ee.event_id = e.id
            )
        )
           OR entity_id IN (
                SELECT e.id
                FROM wu_entities e
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM wu_entity_evidence ee
                    WHERE ee.entity_id = e.id
                )
            )
        """
    )
    op.execute(
        """
        DELETE FROM wu_event_evidence
        WHERE event_id IN (
            SELECT e.id
            FROM wu_historical_events e
            WHERE NOT EXISTS (
                SELECT 1
                FROM wu_event_evidence ee
                WHERE ee.event_id = e.id
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM wu_historical_events
        WHERE NOT EXISTS (
            SELECT 1
            FROM wu_event_evidence ee
            WHERE ee.event_id = wu_historical_events.id
        )
        """
    )

    op.execute(
        """
        DELETE FROM wu_geo_evidence
        WHERE entity_id IN (
            SELECT e.id
            FROM wu_entities e
            WHERE NOT EXISTS (
                SELECT 1
                FROM wu_entity_evidence ee
                WHERE ee.entity_id = e.id
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM wu_geo_features
        WHERE entity_id IN (
            SELECT e.id
            FROM wu_entities e
            WHERE NOT EXISTS (
                SELECT 1
                FROM wu_entity_evidence ee
                WHERE ee.entity_id = e.id
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM wu_alias_index
        WHERE entity_id IN (
            SELECT e.id
            FROM wu_entities e
            WHERE NOT EXISTS (
                SELECT 1
                FROM wu_entity_evidence ee
                WHERE ee.entity_id = e.id
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM wu_entity_evidence
        WHERE entity_id IN (
            SELECT e.id
            FROM wu_entities e
            WHERE NOT EXISTS (
                SELECT 1
                FROM wu_entity_evidence ee
                WHERE ee.entity_id = e.id
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM wu_entities
        WHERE NOT EXISTS (
            SELECT 1
            FROM wu_entity_evidence ee
            WHERE ee.entity_id = wu_entities.id
        )
        """
    )


def downgrade() -> None:
    # Deleted records had no local evidence and cannot be reconstructed.
    pass
