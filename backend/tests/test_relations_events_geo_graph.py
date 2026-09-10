from __future__ import annotations

import pytest
from wu_culture.events import EventCreate, EventService
from wu_culture.geo import GeoFeature, GeoService, SpatialConfidence
from wu_culture.graph import GraphQueryRequest, GraphQueryService
from wu_culture.person_qa import run_person_relation_qa
from wu_culture.relations import RelationCreate, RelationQuery, RelationService, RelationValidationError
from wu_culture.relations.service import RelationType
from wu_culture.spacetime import map_time_label

QIANLONG_12 = "".join(map(chr, [0x4E7E, 0x9686, 0x5341, 0x4E8C, 0x5E74]))


def test_relation_one_hop_and_validation() -> None:
    service = RelationService()
    with pytest.raises(RelationValidationError):
        service.create(RelationCreate(subject_id="a", object_id="b", relation_type=RelationType.LOCATED_IN))
    rel = service.create(
        RelationCreate(
            subject_id="bridge-1",
            object_id="stream-1",
            relation_type=RelationType.CROSSES,
            evidence_ids=("ev-1",),
        )
    )
    out = service.one_hop(RelationQuery(entity_id="bridge-1"))
    assert rel in out
    with pytest.raises(RelationValidationError, match="already exists"):
        service.create(RelationCreate(id=rel.id, subject_id="other", object_id="third", relation_type=RelationType.RELATED_TO, evidence_ids=("ev-2",)))
    with pytest.raises(RelationValidationError, match="unique and non-empty"):
        service.create(RelationCreate(subject_id="other", object_id="third", relation_type=RelationType.RELATED_TO, evidence_ids=("ev-2", "ev-2")))


def test_event_and_time_mapping() -> None:
    events = EventService()
    event = events.create(
        EventCreate(
            title="repair",
            event_type="repair",
            start_time=QIANLONG_12,
            place_entity_id="bridge-1",
            evidence_ids=("ev-1",),
        )
    )
    assert events.get(event.id) is not None
    with pytest.raises(ValueError, match="already exists"):
        events.create(EventCreate(id=event.id, title="duplicate", event_type="repair", evidence_ids=("ev-2",)))
    with pytest.raises(ValueError, match="must not be after"):
        EventCreate(title="bad time", event_type="repair", start_time="2020-01-02", end_time="2020-01-01", evidence_ids=("ev-3",))
    mapped = map_time_label(QIANLONG_12)
    assert mapped.year_start == 1747
    assert mapped.dynasty == "qing"
    assert map_time_label("明代某年").year_start is None
    assert map_time_label("乾隆十二年").confidence < 1


def test_geo_confidence_and_graph_depth_limit() -> None:
    geo = GeoService()
    geo.upsert(
        GeoFeature(
            entity_id="bridge-1",
            name="bridge",
            lon=120.5,
            lat=31.2,
            confidence=SpatialConfidence.APPROXIMATE,
            basis="approx from gazetteer",
            evidence_ids=("ev-1",),
        )
    )
    relations = RelationService()
    relations.create(
        RelationCreate(subject_id="person-1", object_id="bridge-1", relation_type=RelationType.BUILT_BY, evidence_ids=("ev-1",))
    )
    relations.create(
        RelationCreate(subject_id="bridge-1", object_id="stream-1", relation_type=RelationType.CROSSES, evidence_ids=("ev-2",))
    )
    graph = GraphQueryService(relations)
    depth1 = graph.query(GraphQueryRequest(start_entity_id="person-1", max_depth=1))
    assert "bridge-1" in depth1["nodes"]
    assert "stream-1" not in depth1["nodes"]
    depth2 = graph.query(GraphQueryRequest(start_entity_id="person-1", max_depth=2))
    assert "stream-1" in depth2["nodes"]
    assert depth1["truncated"] is False
    limited = graph.query(GraphQueryRequest(start_entity_id="person-1", max_depth=2, max_nodes=2))
    assert limited["truncated"] is True
    with pytest.raises(ValueError, match="finite"):
        geo.upsert(GeoFeature(entity_id="bad", name="bad", lon=float("nan"), lat=31.2, confidence=SpatialConfidence.EXACT, basis="test"))
    with pytest.raises(ValueError, match="unique and non-empty"):
        GeoFeature(entity_id="bad", name="bad", lon=120, lat=31, confidence=SpatialConfidence.EXACT, basis="test", evidence_ids=("ev-1", "ev-1"))


def test_person_relation_qa_loop() -> None:
    relations = RelationService()
    relations.create(
        RelationCreate(
            subject_id="person-1",
            object_id="bridge-1",
            relation_type=RelationType.BUILT_BY,
            evidence_ids=("ev-1",),
        )
    )
    result = run_person_relation_qa(relations, person_id="person-1", person_name="person")
    assert result["status"] == "answered"
    assert "ev-1" in result["answer"]
    empty = run_person_relation_qa(RelationService(), person_id="nobody", person_name="none")
    assert empty["status"] == "refused"
    with pytest.raises(ValueError, match="person_name"):
        run_person_relation_qa(relations, person_id="person-1", person_name=" ")
