from __future__ import annotations

from pathlib import Path

from wu_culture.models import ReviewStatus

from deerflow.persistence.wu_culture.knowledge_seed import load_knowledge_seed
from deerflow.persistence.wu_culture.knowledge_seed import seed_evidence_chunk_id


def test_fuxianzhi_seed_is_deterministic_evidence_bound_and_pending() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "fuxianzhi_knowledge_seed.json"
    seed = load_knowledge_seed(path)

    assert seed.schema_version == "fuxianzhi-knowledge-seed-v1"
    assert len(seed.entities) >= 12
    assert len(seed.relations) >= 10
    assert len(seed.events) >= 6
    assert len(seed.geo_features) >= 5
    all_records = (*seed.entities, *seed.relations, *seed.events, *seed.geo_features)
    assert all(record.review_status is ReviewStatus.PENDING for record in all_records)
    assert all(record.evidence_ids for record in all_records)

    ids = [record.id for record in (*seed.entities, *seed.relations, *seed.events)]
    assert len(ids) == len(set(ids))
    assert len({record.entity_id for record in seed.geo_features}) == len(seed.geo_features)


def test_fuxianzhi_seed_references_declared_entities() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "fuxianzhi_knowledge_seed.json"
    seed = load_knowledge_seed(path)
    entity_ids = {record.id for record in seed.entities}

    assert all(relation.subject_id in entity_ids and relation.object_id in entity_ids for relation in seed.relations)
    assert all((event.place_entity_id is None or event.place_entity_id in entity_ids) and set(event.participant_entity_ids) <= entity_ids for event in seed.events)
    assert all(feature.entity_id in entity_ids for feature in seed.geo_features)


def test_seed_evidence_ids_are_rebound_by_stable_chunk_id() -> None:
    old_release_id = "fulltext-release-old-version-chunk-deadbeef"

    assert seed_evidence_chunk_id(old_release_id) == "chunk-deadbeef"
    assert seed_evidence_chunk_id("evidence-chunk-deadbeef") == "chunk-deadbeef"
