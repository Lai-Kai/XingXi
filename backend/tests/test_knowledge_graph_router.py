from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from wu_culture.entities import EntityRecord
from wu_culture.events import EventRecord
from wu_culture.geo import GeoFeature
from wu_culture.graph import InMemoryKnowledgeGraphRepository
from wu_culture.models import EntityType, ReviewStatus
from wu_culture.relations import RelationRecord

from app.gateway.routers import knowledge_graph


@dataclass
class _User:
    system_role: str


class _GraphRepository:
    def __init__(self) -> None:
        self.relations: dict[str, RelationRecord] = {}

    async def list_relations(self, **_kwargs) -> list[RelationRecord]:
        return list(self.relations.values())

    async def create_relation(self, body) -> RelationRecord:  # noqa: ANN001
        if not body.evidence_ids and not body.is_inferred:
            raise ValueError("relation requires evidence or is_inferred=true")
        record = RelationRecord(id=body.id or "rel-created", **body.model_dump(exclude={"id"}))
        self.relations[record.id] = record
        return record

    async def delete_relation(self, relation_id: str) -> bool:
        return self.relations.pop(relation_id, None) is not None

    async def review_relation(self, relation_id: str, review_status: ReviewStatus) -> RelationRecord:
        record = self.relations.get(relation_id)
        if record is None:
            raise KeyError(relation_id)
        if review_status is ReviewStatus.REVIEWED and not record.evidence_ids:
            raise ValueError("reviewed relations require at least one evidence_id")
        updated = record.model_copy(update={"review_status": review_status})
        self.relations[relation_id] = updated
        return updated


class _EventRepository:
    def __init__(self) -> None:
        self.events: dict[str, EventRecord] = {}

    async def list(self, **_kwargs) -> list[EventRecord]:
        return list(self.events.values())

    async def create(self, body) -> EventRecord:  # noqa: ANN001
        if not body.evidence_ids and not body.is_inferred:
            raise ValueError("event requires evidence or is_inferred=true")
        record = EventRecord(id=body.id or "event-created", **body.model_dump(exclude={"id"}))
        self.events[record.id] = record
        return record

    async def delete(self, event_id: str) -> bool:
        return self.events.pop(event_id, None) is not None

    async def review(self, event_id: str, review_status: ReviewStatus) -> EventRecord:
        record = self.events.get(event_id)
        if record is None:
            raise KeyError(event_id)
        if review_status is ReviewStatus.REVIEWED and not record.evidence_ids:
            raise ValueError("reviewed events require at least one evidence_id")
        updated = record.model_copy(update={"review_status": review_status})
        self.events[event_id] = updated
        return updated


class _GeoRepository:
    def __init__(self) -> None:
        self.features: dict[str, GeoFeature] = {}

    async def list(self, **_kwargs) -> list[GeoFeature]:
        return list(self.features.values())

    async def upsert(self, body: GeoFeature) -> GeoFeature:
        self.features[body.entity_id] = body
        return body

    async def delete(self, entity_id: str) -> bool:
        return self.features.pop(entity_id, None) is not None


def _client(monkeypatch, *, role: str | None) -> tuple[TestClient, _GraphRepository, _EventRepository, _GeoRepository]:
    graph = _GraphRepository()
    events = _EventRepository()
    geo = _GeoRepository()
    app = FastAPI()
    app.include_router(knowledge_graph.router)
    app.dependency_overrides[knowledge_graph.get_graph_repository] = lambda: graph
    app.dependency_overrides[knowledge_graph.get_event_repository] = lambda: events
    app.dependency_overrides[knowledge_graph.get_geo_repository] = lambda: geo

    async def current_user(_request):  # noqa: ANN001
        if role is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return _User(role)

    async def admin_user(_request, *, detail: str):  # noqa: ANN001
        if role is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        if role != "admin":
            raise HTTPException(status_code=403, detail=detail)

    monkeypatch.setattr(knowledge_graph, "get_current_user_from_request", current_user)
    monkeypatch.setattr(knowledge_graph, "require_admin_user", admin_user)
    return TestClient(app), graph, events, geo


def test_reads_require_authentication(monkeypatch) -> None:
    client, *_ = _client(monkeypatch, role=None)
    assert client.get("/api/knowledge-graph/relations").status_code == 401
    assert client.get("/api/knowledge-graph/events").status_code == 401
    assert client.get("/api/knowledge-graph/geo").status_code == 401
    assert client.post("/api/knowledge-graph/gloss", json={"text": "香溪有桥。"}).status_code == 401


def test_graph_query_exposes_requested_network_and_release_scope(monkeypatch) -> None:
    client, *_ = _client(monkeypatch, role="user")
    repository = InMemoryKnowledgeGraphRepository(
        entities=[EntityRecord(id=node_id, canonical_name=node_id, entity_type=EntityType.PLACE) for node_id in ("a", "b", "c", "d")],
        relations=[RelationRecord(id=f"edge-{index}", subject_id=left, object_id=right, relation_type="related_to", evidence_ids=(f"ev-{index}",), confidence=0.8) for index, (left, right) in enumerate((("a", "b"), ("b", "c"), ("c", "d")))],
        evidence=[{"evidence_id": f"ev-{index}", "document_title": "测试方志", "page_start": index + 1} for index in range(3)],
    )
    client.app.dependency_overrides[knowledge_graph.get_graph_repository] = lambda: repository

    async def release_id(requested):
        return requested or "release-active"

    monkeypatch.setattr(knowledge_graph, "_resolve_active_release_id", release_id)
    for depth in (1, 2, 3):
        response = client.get(f"/api/knowledge-graph/query?entity=a&max_depth={depth}&max_nodes=10&release_id=release-frozen")
        assert response.status_code == 200
        payload = response.json()
        assert payload["release_id"] == "release-frozen"
        assert payload["max_depth"] == depth
        assert payload["max_nodes"] == 10
        assert len(payload["nodes"]) == depth + 1
        assert len(payload["edges"]) == depth
        assert len(payload["evidence"]) == depth
    assert client.get("/api/knowledge-graph/query?entity=a&max_depth=4").status_code == 422


def test_ordinary_user_can_read_but_cannot_write(monkeypatch) -> None:
    client, *_ = _client(monkeypatch, role="user")
    assert client.get("/api/knowledge-graph/relations").status_code == 200
    response = client.post(
        "/api/knowledge-graph/relations",
        json={
            "subject_id": "entity-a",
            "relation_type": "related_to",
            "object_id": "entity-b",
            "is_inferred": True,
        },
    )
    assert response.status_code == 403


def test_ordinary_user_can_create_reading_aid_label(monkeypatch) -> None:
    client, *_ = _client(monkeypatch, role="user")
    response = client.post(
        "/api/knowledge-graph/gloss",
        json={
            "text": "香溪有桥，始建未详。",
            "title": "香溪桥记释读",
            "object_name": "香溪桥",
            "source_title": "地方文献摘录",
            "volume": "卷一",
            "page": "第12页",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "香溪桥记释读"
    assert payload["source_title"] == "地方文献摘录"
    assert payload["status"] == "reading_aid"
    assert payload["gloss"]["original"] == "香溪有桥，始建未详。"
    assert payload["gloss"]["sentences"]


def test_admin_can_manage_inferred_relation_event_and_geo(monkeypatch) -> None:
    client, *_ = _client(monkeypatch, role="admin")
    relation = client.post(
        "/api/knowledge-graph/relations",
        json={
            "id": "rel-demo",
            "subject_id": "entity-a",
            "relation_type": "related_to",
            "object_id": "entity-b",
            "is_inferred": True,
            "review_status": "pending",
        },
    )
    assert relation.status_code == 201
    assert client.get("/api/knowledge-graph/relations").json()[0]["id"] == "rel-demo"

    event = client.post(
        "/api/knowledge-graph/events",
        json={
            "id": "event-demo",
            "title": "演示事件",
            "event_type": "demo",
            "is_inferred": True,
            "review_status": "pending",
        },
    )
    assert event.status_code == 201
    assert client.get("/api/knowledge-graph/events").json()[0]["id"] == "event-demo"

    assert (
        client.patch(
            "/api/knowledge-graph/relations/rel-demo/review",
            json={"review_status": "reviewed"},
        ).status_code
        == 400
    )
    assert (
        client.patch(
            "/api/knowledge-graph/relations/rel-demo/review",
            json={"review_status": "rejected"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/knowledge-graph/events/event-demo/review",
            json={"review_status": "reviewed"},
        ).status_code
        == 400
    )
    assert (
        client.patch(
            "/api/knowledge-graph/events/event-demo/review",
            json={"review_status": "rejected"},
        ).status_code
        == 200
    )

    feature = client.put(
        "/api/knowledge-graph/geo/entity-a",
        json={
            "entity_id": "entity-a",
            "name": "演示点",
            "lon": 120.5,
            "lat": 31.25,
            "confidence": "speculative",
            "basis": "仅用于功能验证",
            "review_status": ReviewStatus.PENDING.value,
        },
    )
    assert feature.status_code == 200
    assert client.get("/api/knowledge-graph/geo").json()[0]["name"] == "演示点"

    assert client.delete("/api/knowledge-graph/relations/rel-demo").status_code == 204
    assert client.delete("/api/knowledge-graph/events/event-demo").status_code == 204
    assert client.delete("/api/knowledge-graph/geo/entity-a").status_code == 204


def test_non_inferred_records_require_evidence(monkeypatch) -> None:
    client, *_ = _client(monkeypatch, role="admin")
    relation = client.post(
        "/api/knowledge-graph/relations",
        json={
            "subject_id": "entity-a",
            "relation_type": "related_to",
            "object_id": "entity-b",
        },
    )
    event = client.post(
        "/api/knowledge-graph/events",
        json={"title": "无证据事件", "event_type": "demo"},
    )
    assert relation.status_code == 400
    assert event.status_code == 400
