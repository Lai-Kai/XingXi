from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from wu_culture.entities import EntityRecord
from wu_culture.relations.service import RelationRecord, RelationService, RelationType


def _relation_sort_key(relation: RelationRecord) -> tuple[int, int, int, float, str]:
    """Prefer factual edges when a bounded neighborhood cannot show everything."""
    relation_type = (
        relation.relation_type.value
        if hasattr(relation.relation_type, "value")
        else str(relation.relation_type)
    )
    return (
        int(relation_type == RelationType.DOCUMENTED_IN.value),
        int(relation.is_inferred),
        -len(relation.evidence_ids),
        -relation.confidence,
        relation.id,
    )


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class GraphQueryRequest(_M):
    start_entity_id: str = Field(min_length=1)
    max_depth: int = Field(default=1, ge=1, le=3)
    max_nodes: int = Field(default=50, ge=1, le=200)


class GraphQueryService:
    """One/few-hop neighborhood queries with NetworkX-backed cycle safety.

    Data remains in the relation table / RelationService. NetworkX is only used
    for bounded traversal and cycle detection (stage 33 tech stack choice).
    """

    def __init__(self, relations: RelationService) -> None:
        self._relations = relations

    def _build_graph(self, seed: str, *, max_depth: int, max_nodes: int) -> tuple[nx.DiGraph, list[RelationRecord]]:
        graph = nx.DiGraph()
        graph.add_node(seed)
        edges: list[RelationRecord] = []
        frontier = {seed}
        for _depth in range(max_depth):
            if len(graph) >= max_nodes:
                break
            next_frontier: set[str] = set()
            for node in frontier:
                for rel in self._relations.one_hop(
                    type("Q", (), {"entity_id": node, "direction": "both", "limit": max_nodes})()
                ):
                    edges.append(rel)
                    graph.add_edge(
                        rel.subject_id,
                        rel.object_id,
                        relation_type=rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type),
                        evidence_ids=list(rel.evidence_ids),
                        relation_id=rel.id,
                    )
                    if len(graph) >= max_nodes:
                        break
                    for endpoint in (rel.subject_id, rel.object_id):
                        if endpoint not in graph:
                            graph.add_node(endpoint)
                        if endpoint != node and endpoint not in frontier:
                            next_frontier.add(endpoint)
                if len(graph) >= max_nodes:
                    break
            frontier = next_frontier
            if not frontier:
                break
        return graph, edges

    def query(self, request: GraphQueryRequest) -> dict:
        graph, edges = self._build_graph(
            request.start_entity_id,
            max_depth=request.max_depth,
            max_nodes=request.max_nodes,
        )
        # Bounded ego neighborhood for stable node membership.
        all_nodes = set(nx.ego_graph(graph.to_undirected(as_view=True), request.start_entity_id, radius=request.max_depth).nodes())
        nodes = set(all_nodes)
        nodes.add(request.start_entity_id)
        if len(nodes) > request.max_nodes:
            # Preserve start node and nearest nodes by BFS order.
            ordered = [request.start_entity_id]
            for node in nx.bfs_tree(graph.to_undirected(as_view=True), request.start_entity_id):
                if node not in ordered:
                    ordered.append(node)
                if len(ordered) >= request.max_nodes:
                    break
            nodes = set(ordered)
        filtered_edges = [
            edge for edge in edges
            if edge.subject_id in nodes and edge.object_id in nodes
        ]
        # Cycle detection never expands infinitely because depth/nodes are capped.
        undirected = graph.to_undirected()
        has_cycle = False
        try:
            has_cycle = any(True for _ in nx.simple_cycles(graph)) if graph.number_of_edges() else False
        except nx.NetworkXNoCycle:
            has_cycle = False
        if not has_cycle and undirected.number_of_edges():
            has_cycle = not nx.is_forest(undirected.subgraph(nodes))
        return {
            "start_entity_id": request.start_entity_id,
            "max_depth": request.max_depth,
            "nodes": sorted(nodes),
            "edges": [edge.model_dump(mode="json") for edge in filtered_edges[: request.max_nodes]],
            # Reaching the caller's bound means traversal may have stopped before
            # examining the next frontier; report it as potentially truncated.
            "truncated": len(all_nodes) >= request.max_nodes or len(filtered_edges) > request.max_nodes,
            "has_cycle": has_cycle,
            "engine": "networkx",
        }

    def detect_cycles(self, relations: Iterable[RelationRecord] | None = None) -> list[list[str]]:
        graph = nx.DiGraph()
        source = relations if relations is not None else self._relations.list_all() if hasattr(self._relations, "list_all") else []
        if relations is None and not source:
            # Fall back to scanning known endpoints via one-hop on empty seed is useless;
            # RelationService stores items internally.
            items = getattr(self._relations, "_items", {})
            source = list(items.values()) if isinstance(items, dict) else []
        for rel in source:
            graph.add_edge(rel.subject_id, rel.object_id)
        cycles: list[list[str]] = []
        for cycle in nx.simple_cycles(graph):
            cycles.append(cycle)
            if len(cycles) >= 20:
                break
        return cycles


class KnowledgeGraphRepository(Protocol):
    async def resolve_entities(
        self, query: str, *, release_id: str | None = None, limit: int = 10
    ) -> list[EntityRecord]: ...

    async def get_entities(
        self, entity_ids: Sequence[str], *, release_id: str | None = None
    ) -> list[EntityRecord]: ...

    async def relations_for_entities(
        self,
        entity_ids: Sequence[str],
        *,
        release_id: str | None = None,
        relation_types: Sequence[str] | None = None,
        limit: int = 200,
    ) -> list[RelationRecord]: ...

    async def evidence_locators(self, evidence_ids: Sequence[str]) -> list[dict]: ...


class InMemoryKnowledgeGraphRepository:
    def __init__(
        self,
        *,
        entities: Sequence[EntityRecord] = (),
        relations: Sequence[RelationRecord] = (),
        evidence: Sequence[dict] = (),
    ) -> None:
        self._entities = {entity.id: entity for entity in entities}
        self._relations = {relation.id: relation for relation in relations}
        self._evidence = {str(item["evidence_id"]): dict(item) for item in evidence}

    async def resolve_entities(
        self, query: str, *, release_id: str | None = None, limit: int = 10
    ) -> list[EntityRecord]:
        normalized = query.casefold()
        if query in self._entities:
            return [self._entities[query]]
        exact = [entity for entity in self._entities.values() if entity.canonical_name.casefold() == normalized]
        rows = exact or [entity for entity in self._entities.values() if normalized in entity.canonical_name.casefold()]
        return sorted(rows, key=lambda entity: (entity.canonical_name, entity.entity_type.value, entity.id))[:limit]

    async def get_entities(
        self, entity_ids: Sequence[str], *, release_id: str | None = None
    ) -> list[EntityRecord]:
        return sorted(
            (self._entities[entity_id] for entity_id in set(entity_ids) if entity_id in self._entities),
            key=lambda entity: entity.id,
        )

    async def relations_for_entities(
        self,
        entity_ids: Sequence[str],
        *,
        release_id: str | None = None,
        relation_types: Sequence[str] | None = None,
        limit: int = 200,
    ) -> list[RelationRecord]:
        ids = set(entity_ids)
        allowed = set(relation_types or ())
        rows = [
            relation
            for relation in self._relations.values()
            if (relation.subject_id in ids or relation.object_id in ids)
            and (not allowed or relation.relation_type.value in allowed)
        ]
        return sorted(rows, key=_relation_sort_key)[:limit]

    async def evidence_locators(self, evidence_ids: Sequence[str]) -> list[dict]:
        return [self._evidence[evidence_id] for evidence_id in evidence_ids if evidence_id in self._evidence]


class PersistentGraphQueryService:
    """Resolve an entity and traverse a bounded SQL- or memory-backed graph."""

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repository = repository

    async def query(
        self,
        *,
        entity: str,
        max_depth: int = 2,
        max_nodes: int = 50,
        relation_types: Sequence[str] | None = None,
        release_id: str | None = None,
    ) -> dict:
        candidates = await self._repository.resolve_entities(entity, release_id=release_id, limit=10)
        candidate_payloads = [self._entity_payload(candidate) for candidate in candidates]
        empty = {
            "query": entity,
            "candidates": candidate_payloads,
            "nodes": [],
            "edges": [],
            "evidence": [],
            "truncated": False,
        }
        if not candidates:
            return {
                **empty,
                "status": "empty",
                "message": "No matching entity is currently available in the knowledge graph.",
            }
        if len(candidates) > 1:
            return {
                **empty,
                "status": "ambiguous",
                "message": "Multiple entities match this name; use an entity ID or add a type qualifier.",
            }

        start_id = candidates[0].id
        node_ids = {start_id}
        frontier = {start_id}
        collected: dict[str, RelationRecord] = {}
        truncated = False
        for _depth in range(max_depth):
            if not frontier:
                break
            relation_limit = max(200, max_nodes * 8)
            relations = await self._repository.relations_for_entities(
                sorted(frontier),
                release_id=release_id,
                relation_types=relation_types,
                limit=relation_limit,
            )
            if len(relations) >= relation_limit:
                truncated = True
            next_frontier: set[str] = set()
            for relation in sorted(relations, key=_relation_sort_key):
                endpoints = (relation.subject_id, relation.object_id)
                if not (set(endpoints) & frontier):
                    continue
                new_ids = [endpoint for endpoint in endpoints if endpoint not in node_ids]
                if len(node_ids) + len(new_ids) > max_nodes:
                    truncated = True
                    continue
                collected[relation.id] = relation
                node_ids.update(new_ids)
                next_frontier.update(new_ids)
            frontier = next_frontier

        nodes = await self._repository.get_entities(sorted(node_ids), release_id=release_id)
        known_ids = {node.id for node in nodes}
        edges = [
            relation
            for relation in sorted(collected.values(), key=_relation_sort_key)
            if relation.subject_id in known_ids and relation.object_id in known_ids
        ]
        evidence_ids = sorted({evidence_id for edge in edges for evidence_id in edge.evidence_ids})
        evidence = await self._repository.evidence_locators(evidence_ids)
        return {
            "query": entity,
            "status": "supported",
            "message": "Knowledge graph relationships found.",
            "candidates": candidate_payloads,
            "nodes": [self._entity_payload(node) for node in nodes],
            "edges": [relation.model_dump(mode="json") for relation in edges],
            "evidence": evidence,
            "truncated": truncated,
        }

    @staticmethod
    def _entity_payload(entity: EntityRecord) -> dict:
        return entity.model_dump(
            mode="json",
            include={
                "id",
                "canonical_name",
                "entity_type",
                "dynasty",
                "extant_status",
                "summary",
                "review_status",
                "release_id",
                "evidence_ids",
            },
        )
