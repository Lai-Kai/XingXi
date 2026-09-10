from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from wu_culture.entities import EntityRecord
from wu_culture.events import EventRecord, TimeCertainty
from wu_culture.models import EntityType, ReviewStatus
from wu_culture.relations import RelationRecord, RelationType

from app.gateway.routers import map_points


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(map_points.router)
    return TestClient(app)


class _VersionedCatalogSource:
    async def load(self):
        return map_points.MapCatalogOut(
            updated_at="2026-08-22",
            data_notice="府县志内部工作版本，待复核。",
            points=(
                map_points.MapPointOut(
                    id="corpus-place-1",
                    entity_id="place-1",
                    name="香溪",
                    entity_type="waterway",
                    lon=120.5,
                    lat=31.2,
                    confidence="approximate",
                    basis="府县志证据与现代同名地物交叉定位",
                    geometry_type="historical_area",
                    area_coordinates=(
                        (120.49, 31.19),
                        (120.51, 31.19),
                        (120.51, 31.21),
                        (120.49, 31.21),
                        (120.49, 31.19),
                    ),
                    extent_source="historical_map",
                    extent_basis="历史舆图约示范围，不是现代地籍边界。",
                    dynasties=("qing",),
                    heritage_status="uncertain",
                    access_status="verify_before_visit",
                    summary="待复核的府县志地点。",
                    address="历史地点，范围待核",
                    review_status=ReviewStatus.PENDING,
                    release_id="release-working",
                    record_kind="corpus",
                    evidence=(
                        map_points.MapEvidenceOut(
                            id="evidence-1",
                            title="吴县志卷一",
                            publisher="府县志内部语料",
                            url="/api/knowledge-search/evidence/evidence-1",
                            kind="corpus_evidence",
                            note="第 12 页",
                        ),
                    ),
                ),
            ),
            layers=(),
            events=(),
            trajectories=(),
            routes=(),
        )


def test_map_catalog_merges_versioned_corpus_features() -> None:
    app = FastAPI()
    app.include_router(map_points.router)
    app.dependency_overrides[map_points.get_versioned_catalog_source] = lambda: _VersionedCatalogSource()

    with TestClient(app) as client:
        response = client.get("/api/map/catalog")
        points_response = client.get("/api/map/points")

    assert response.status_code == 200
    payload = response.json()
    assert [point["id"] for point in payload["points"]] == ["corpus-place-1"]
    corpus_point = next(point for point in payload["points"] if point["id"] == "corpus-place-1")
    assert corpus_point["evidence"][0]["kind"] == "corpus_evidence"
    assert corpus_point["evidence"][0]["url"] == "/api/knowledge-search/evidence/evidence-1"
    assert corpus_point["review_status"] == "pending"
    assert corpus_point["release_id"] == "release-working"
    assert corpus_point["record_kind"] == "corpus"
    assert corpus_point["geometry_type"] == "historical_area"
    assert len(corpus_point["area_coordinates"]) == 5
    assert corpus_point["extent_source"] == "historical_map"
    assert "内部工作版本" in payload["data_notice"]

    points = points_response.json()
    assert any(point["id"] == "corpus-place-1" for point in points)


def test_map_catalog_uses_traceable_non_demo_sources() -> None:
    with _client() as client:
        response = client.get("/api/map/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated_at"] == "2026-07-29"
    assert len(payload["points"]) >= 8
    serialized = response.text.lower()
    assert "synthetic-evidence" not in serialized
    assert '"basis":"demo"' not in serialized
    for point in payload["points"]:
        assert point["coordinate_system"] == "WGS84"
        assert point["confidence"] in {"exact", "approximate", "speculative"}
        if point["confidence"] == "exact":
            assert point["geometry_type"] == "point"
        else:
            assert point["geometry_type"] in {"uncertainty_radius", "historical_area"}
            assert point["uncertainty_radius_m"] or point["area_coordinates"]
            assert point["extent_basis"]
        assert point["basis"]
        assert point["evidence"]
        assert all(source["url"].startswith("https://") for source in point["evidence"])


def test_map_points_support_combined_business_filters() -> None:
    with _client() as client:
        response = client.get(
            "/api/map/points",
            params={
                "entity_type": "garden",
                "dynasty": "qing",
                "min_confidence": "exact",
                "heritage_status": "extant",
                "query": "花园",
            },
        )

    assert response.status_code == 200
    points = response.json()
    assert points
    assert all(point["entity_type"] == "garden" for point in points)
    assert all("qing" in point["dynasties"] for point in points)
    assert all(point["confidence"] == "exact" for point in points)
    assert all(point["heritage_status"] == "extant" for point in points)


def test_unverified_historical_map_is_not_exposed_as_overlay() -> None:
    with _client() as client:
        response = client.get("/api/map/layers")

    assert response.status_code == 200
    layers = response.json()
    assert any(layer["kind"] == "base" and layer["available"] for layer in layers)
    historical = [layer for layer in layers if layer["kind"] == "historical"]
    assert historical
    assert all(not layer["available"] for layer in historical)
    assert all(layer["calibration_note"] and layer["source_url"] for layer in historical)


def test_timeline_trajectory_and_routes_preserve_uncertainty() -> None:
    with _client() as client:
        timeline = client.get("/api/map/events").json()
        trajectories = client.get("/api/map/trajectories").json()
        routes = client.get("/api/map/routes").json()

    assert timeline
    assert all(event["evidence"] for event in timeline)
    assert all(event["featured"] for event in timeline)
    assert {event["importance"] for event in timeline} <= {"landmark", "notable"}
    assert trajectories
    assert all(node["evidence"] for item in trajectories for node in item["points"])
    assert any(item["has_uncertain_segments"] for item in trajectories)
    assert routes
    assert all(route["disclaimer"] for route in routes)
    assert all(route["stop_ids"] for route in routes)


def test_person_trajectories_are_derived_from_events_and_person_place_relations() -> None:
    evidence = (
        map_points.MapEvidenceOut(
            id="evidence-1",
            title="吴县志",
            publisher="府县志内部语料",
            url="/api/knowledge-search/evidence/evidence-1",
            kind="corpus_evidence",
            note="第 12 页；pending",
        ),
    )
    mudu = map_points.MapPointOut(
        id="corpus-place-mudu",
        entity_id="place-mudu",
        name="木渎",
        entity_type="place",
        lon=120.5067,
        lat=31.2530,
        confidence="approximate",
        basis="府县志与现代同名地物交叉定位",
        dynasties=("qing",),
        heritage_status="extant",
        access_status="verify_before_visit",
        summary="木渎镇",
        address="历史地点",
        evidence=evidence,
        review_status=ReviewStatus.PENDING,
        release_id="release-working",
        record_kind="corpus",
    )
    lingyan = mudu.model_copy(
        update={
            "id": "corpus-place-lingyan",
            "entity_id": "place-lingyan",
            "name": "灵岩山",
            "confidence": "speculative",
        }
    )
    entities = {
        "person-kangxi": EntityRecord(
            id="person-kangxi",
            canonical_name="康熙帝",
            entity_type=EntityType.PERSON,
            review_status=ReviewStatus.PENDING,
            release_id="release-working",
            evidence_ids=("evidence-1",),
        ),
        "place-mudu": EntityRecord(
            id="place-mudu",
            canonical_name="木渎",
            entity_type=EntityType.PLACE,
            review_status=ReviewStatus.PENDING,
            release_id="release-working",
            evidence_ids=("evidence-1",),
        ),
        "place-lingyan": EntityRecord(
            id="place-lingyan",
            canonical_name="灵岩山",
            entity_type=EntityType.PLACE,
            review_status=ReviewStatus.PENDING,
            release_id="release-working",
            evidence_ids=("evidence-1",),
        ),
    }
    events = (
        EventRecord(
            id="event-kangxi-mudu",
            title="康熙帝至木渎",
            event_type="imperial_visit",
            start_time="1689",
            time_certainty=TimeCertainty.EXACT,
            place_entity_id="place-mudu",
            participant_entity_ids=("person-kangxi",),
            evidence_ids=("evidence-1",),
            review_status=ReviewStatus.PENDING,
            release_id="release-working",
        ),
    )
    relations = (
        RelationRecord(
            id="rel-kangxi-lingyan",
            subject_id="person-kangxi",
            relation_type=RelationType.VISITED,
            object_id="place-lingyan",
            start_time="1689",
            confidence=0.8,
            evidence_ids=("evidence-1",),
            review_status=ReviewStatus.PENDING,
            release_id="release-working",
        ),
    )
    evidence_records = {
        "evidence-1": SimpleNamespace(
            document=SimpleNamespace(
                title="吴县志",
                source_institution="府县志内部语料",
                created_at=None,
                updated_at=None,
            ),
            chunk=SimpleNamespace(page_start=12, page_end=12),
            evidence=SimpleNamespace(review_status=ReviewStatus.PENDING),
        )
    }

    trajectories = map_points._derive_person_trajectories(
        points=(mudu, lingyan),
        entities=entities,
        events=events,
        relations=relations,
        evidence_records=evidence_records,
    )

    assert len(trajectories) == 1
    assert trajectories[0].person_name == "康熙帝"
    assert [point.point_id for point in trajectories[0].points] == [
        "corpus-place-mudu",
        "corpus-place-lingyan",
    ]
    assert trajectories[0].review_status is ReviewStatus.PENDING
    assert trajectories[0].has_uncertain_segments is True
    assert all(point.evidence for point in trajectories[0].points)


def test_map_relations_keep_names_type_time_and_evidence() -> None:
    entities = {
        "person-poet": EntityRecord(
            id="person-poet",
            canonical_name="诗人甲",
            entity_type=EntityType.PERSON,
            review_status=ReviewStatus.PENDING,
            release_id="release-working",
            evidence_ids=("evidence-poetry",),
        ),
        "place-lingyan": EntityRecord(
            id="place-lingyan",
            canonical_name="灵岩山",
            entity_type=EntityType.PLACE,
            review_status=ReviewStatus.PENDING,
            release_id="release-working",
            evidence_ids=("evidence-poetry",),
        ),
    }
    relation = RelationRecord(
        id="rel-poet-composed-lingyan",
        subject_id="person-poet",
        relation_type=RelationType.COMPOSED_AT,
        object_id="place-lingyan",
        start_time="宋代",
        confidence=0.8,
        evidence_ids=("evidence-poetry",),
        review_status=ReviewStatus.PENDING,
        release_id="release-working",
    )

    evidence_record = SimpleNamespace(
        document=SimpleNamespace(
            title="吴县志卷十",
            source_institution="府县志内部语料",
            created_at=None,
            updated_at=None,
        ),
        chunk=SimpleNamespace(page_start=30, page_end=30),
        evidence=SimpleNamespace(
            quote="某人游灵岩，赋诗于山中。",
            review_status=ReviewStatus.PENDING,
        ),
    )
    rows = map_points._map_relations(
        (relation,),
        entities,
        {"evidence-poetry": evidence_record},
    )

    assert len(rows) == 1
    assert rows[0].subject_name == "诗人甲"
    assert rows[0].object_name == "灵岩山"
    assert rows[0].relation_type == "composed_at"
    assert rows[0].start_time == "宋代"
    assert rows[0].evidence[0].quote == "某人游灵岩，赋诗于山中。"
