from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import map_points


class _UnpublishedSource:
    async def load(self):
        return None


def test_model_reference_points_do_not_publish_an_empty_knowledge_catalog() -> None:
    app = FastAPI()
    app.include_router(map_points.router)
    app.dependency_overrides[map_points.get_versioned_catalog_source] = lambda: _UnpublishedSource()
    with TestClient(app) as client:
        catalog = client.get("/api/map/catalog")
        references = client.get("/api/map/reference-points", params=[("point_id", "pt-yongan-bridge"), ("point_id", "pt-mingyue-temple")])
    assert catalog.status_code == 200
    assert catalog.json()["updated_at"] == "unpublished"
    assert catalog.json()["points"] == []
    assert references.status_code == 200
    points = references.json()
    assert {point["id"] for point in points} == {"pt-yongan-bridge", "pt-mingyue-temple"}
    for point in points:
        assert point["record_kind"] == "reference"
        assert point["release_id"] is None
        assert point["coordinate_system"] == "WGS84"
        assert point["evidence"]
    bridge = next(point for point in points if point["id"] == "pt-yongan-bridge")
    assert bridge["confidence"] == "approximate"
    assert bridge["geometry_type"] == "uncertainty_radius"


def test_reference_point_selection_never_geocodes_unknown_ids() -> None:
    app = FastAPI()
    app.include_router(map_points.router)
    with TestClient(app) as client:
        response = client.get("/api/map/reference-points", params={"point_id": "unknown-place"})
    assert response.status_code == 200
    assert response.json() == []


def test_reference_points_remain_exactly_the_curated_records() -> None:
    app = FastAPI()
    app.include_router(map_points.router)
    with TestClient(app) as client:
        response = client.get("/api/map/reference-points")
    assert response.status_code == 200
    assert response.json() == [point.model_dump(mode="json") for point in map_points.POINTS if point.record_kind == "reference"]


def test_reference_events_restore_the_curated_timeline_without_publishing_knowledge() -> None:
    app = FastAPI()
    app.include_router(map_points.router)
    app.dependency_overrides[map_points.get_versioned_catalog_source] = lambda: _UnpublishedSource()
    with TestClient(app) as client:
        before = client.get("/api/map/catalog").json()
        response = client.get("/api/map/reference-events")
        after = client.get("/api/map/catalog").json()
    assert response.status_code == 200
    assert before == after and after["events"] == [] and after["points"] == []
    rows = response.json()
    assert len(rows) == 5
    assert rows == [event.model_dump(mode="json") for event in map_points.EVENTS]
    point_ids = {point.id for point in map_points.POINTS if point.record_kind == "reference"}
    for row in rows:
        assert row["point_id"] in point_ids
        assert row["evidence"] and row["record_kind"] == "reference"
        assert row["release_id"] is None and row["review_status"] is None


def test_reference_events_bind_to_the_exact_selected_point_and_keep_dates() -> None:
    app = FastAPI()
    app.include_router(map_points.router)
    with TestClient(app) as client:
        response = client.get("/api/map/reference-events", params={"point_id": "pt-yongan-bridge"})
        unknown = client.get("/api/map/reference-events", params={"point_id": "unknown-place"})
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["event-yongan-built"]
    assert response.json()[0]["year_start"] == 1497
    assert response.json()[0]["precision"] == "exact"
    assert unknown.status_code == 200 and unknown.json() == []
