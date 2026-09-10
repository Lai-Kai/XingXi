from __future__ import annotations

import pytest
from wu_culture.entities import EntityRecord
from wu_culture.graph import InMemoryKnowledgeGraphRepository
from wu_culture.models import EntityType
from wu_culture.relations import RelationRecord, RelationType

from deerflow.agents.xingxi.tools import (
    build_gloss_ancient_text_tool,
    build_query_knowledge_graph_tool,
    build_xingxi_tools,
)


def _entity(entity_id: str, name: str, entity_type: EntityType) -> EntityRecord:
    return EntityRecord(id=entity_id, canonical_name=name, entity_type=entity_type)


@pytest.mark.asyncio
async def test_graph_tool_is_available_when_the_graph_is_empty() -> None:
    tool = build_query_knowledge_graph_tool(InMemoryKnowledgeGraphRepository())

    result = await tool.ainvoke({"entity": "Mudu", "max_depth": 2})

    assert result == {
        "query": "Mudu",
        "status": "empty",
        "message": "No matching entity is currently available in the knowledge graph.",
        "candidates": [],
        "nodes": [],
        "edges": [],
        "evidence": [],
        "truncated": False,
    }


@pytest.mark.asyncio
async def test_graph_tool_returns_bounded_relationships_and_evidence_ids() -> None:
    repository = InMemoryKnowledgeGraphRepository(
        entities=(
            _entity("person-1", "Builder", EntityType.PERSON),
            _entity("bridge-1", "Old Bridge", EntityType.BRIDGE),
            _entity("waterway-1", "Creek", EntityType.WATERWAY),
        ),
        relations=(
            RelationRecord(
                id="rel-1",
                subject_id="person-1",
                relation_type=RelationType.BUILT_BY,
                object_id="bridge-1",
                confidence=0.9,
                evidence_ids=("ev-1",),
            ),
            RelationRecord(
                id="rel-2",
                subject_id="bridge-1",
                relation_type=RelationType.CROSSES,
                object_id="waterway-1",
                confidence=0.8,
                evidence_ids=("ev-2",),
            ),
        ),
        evidence=(
            {
                "evidence_id": "ev-1",
                "document_title": "Local Gazetteer",
                "volume": "1",
                "section": "Bridges",
                "page_start": 12,
                "page_end": 12,
            },
            {
                "evidence_id": "ev-2",
                "document_title": "Local Gazetteer",
                "volume": "1",
                "section": "Waterways",
                "page_start": 13,
                "page_end": 13,
            },
        ),
    )
    tool = build_query_knowledge_graph_tool(repository)

    result = await tool.ainvoke({"entity": "Builder", "max_depth": 2, "max_nodes": 10})

    assert result["status"] == "supported"
    assert [node["id"] for node in result["nodes"]] == ["bridge-1", "person-1", "waterway-1"]
    assert [edge["id"] for edge in result["edges"]] == ["rel-1", "rel-2"]
    assert result["edges"][0]["evidence_ids"] == ["ev-1"]
    assert result["edges"][1]["evidence_ids"] == ["ev-2"]
    assert [item["evidence_id"] for item in result["evidence"]] == ["ev-1", "ev-2"]


@pytest.mark.asyncio
async def test_graph_tool_does_not_guess_between_same_name_entities() -> None:
    repository = InMemoryKnowledgeGraphRepository(
        entities=(
            _entity("place-1", "East Gate", EntityType.PLACE),
            _entity("building-1", "East Gate", EntityType.BUILDING),
        )
    )
    tool = build_query_knowledge_graph_tool(repository)

    result = await tool.ainvoke({"entity": "East Gate"})

    assert result["status"] == "ambiguous"
    assert [candidate["id"] for candidate in result["candidates"]] == ["building-1", "place-1"]
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["evidence"] == []


def test_all_xingxi_modes_register_the_graph_query_tool() -> None:
    assert [tool.name for tool in build_xingxi_tools(mode="flash")] == [
        "search_sources",
        "query_knowledge_graph",
        "query_timeline",
        "query_map_features",
        "gloss_ancient_text",
        "resolve_name_variants",
    ]
    assert [tool.name for tool in build_xingxi_tools(mode="pro")] == [
        "search_sources",
        "query_knowledge_graph",
        "query_timeline",
        "query_map_features",
        "gloss_ancient_text",
        "resolve_name_variants",
        "compare_sources",
    ]
    assert [tool.name for tool in build_xingxi_tools(mode="ultra")] == [
        "search_sources",
        "query_knowledge_graph",
        "query_timeline",
        "query_map_features",
        "gloss_ancient_text",
        "resolve_name_variants",
        "compare_sources",
    ]


def test_all_xingxi_tool_call_schemas_are_json_serializable() -> None:
    for tool in build_xingxi_tools(mode="ultra"):
        schema = tool.tool_call_schema.model_json_schema()

        assert schema["type"] == "object"
        assert "runtime" not in schema.get("properties", {})


def test_ancient_text_tool_preserves_the_original_passage() -> None:
    result = build_gloss_ancient_text_tool().invoke({"text": "Sample classical passage."})

    assert result["original"] == "Sample classical passage."
    assert result["sentences"][0]["original"] == "Sample classical passage."
    assert result["notes"]
