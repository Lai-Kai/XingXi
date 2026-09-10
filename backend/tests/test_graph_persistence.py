from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture.graph import PersistentGraphQueryService

from deerflow.agents.xingxi.tools import build_query_knowledge_graph_tool
from deerflow.persistence.base import Base
from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade
from deerflow.persistence.wu_culture.graph_repository import SqlKnowledgeGraphRepository
from deerflow.persistence.wu_culture.model import (
    WU_CULTURE_TABLES,
    EvidenceRow,
    WuEntityEvidenceRow,
    WuEntityRow,
    WuRelationEvidenceRow,
    WuRelationRow,
)


@pytest.mark.asyncio
async def test_sql_graph_tool_does_not_publish_entities_without_evidence(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=WU_CULTURE_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all(
            [
                WuEntityRow(
                    id="person-1",
                    canonical_name="Researcher",
                    entity_type="person",
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                WuEntityRow(
                    id="place-1",
                    canonical_name="Mudu",
                    entity_type="place",
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                WuRelationRow(
                    id="rel-1",
                    subject_id="person-1",
                    relation_type="related_to",
                    object_id="place-1",
                    confidence=0.4,
                    is_inferred=True,
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    try:
        tool = build_query_knowledge_graph_tool(SqlKnowledgeGraphRepository(factory))
        result = await tool.ainvoke({"entity": "Researcher", "max_depth": 1})

        assert result["status"] == "empty"
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["evidence"] == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_graph_resolves_simplified_name_against_traditional_entity(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'script-variant.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=WU_CULTURE_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        session.add(
            WuEntityRow(
                id="place-mudu-traditional",
                canonical_name="木瀆",
                entity_type="place",
                review_status="pending",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            WuEntityRow(
                id="place-lingyan-mixed-script",
                canonical_name="靈岩山",
                entity_type="place",
                review_status="pending",
                created_at=now,
                updated_at=now,
                )
            )
        session.add_all(
            [
                EvidenceRow(
                    id="evidence-script-mudu",
                    document_id="document-script",
                    chunk_id="chunk-script",
                    quote="木瀆與靈岩山。",
                    source_level="A",
                    review_status="reviewed",
                ),
                WuEntityEvidenceRow(entity_id="place-mudu-traditional", evidence_id="evidence-script-mudu"),
                WuEntityEvidenceRow(entity_id="place-lingyan-mixed-script", evidence_id="evidence-script-mudu"),
            ]
        )
        await session.commit()

    try:
        repository = SqlKnowledgeGraphRepository(factory)
        matches = await repository.resolve_entities("木渎")
        assert [match.canonical_name for match in matches] == ["木瀆"]
        matches = await repository.resolve_entities("灵岩山")
        assert [match.canonical_name for match in matches] == ["靈岩山"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_persistent_graph_keeps_substantive_edges_before_document_links(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph-priority.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=WU_CULTURE_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all(
            [
                WuEntityRow(
                    id="entity-root",
                    canonical_name="主体",
                    entity_type="person",
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                WuEntityRow(
                    id="entity-doc-a",
                    canonical_name="文献甲",
                    entity_type="work",
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                WuEntityRow(
                    id="entity-doc-b",
                    canonical_name="文献乙",
                    entity_type="work",
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                WuEntityRow(
                    id="entity-place",
                    canonical_name="旧址",
                    entity_type="place",
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.add_all(
            [
                EvidenceRow(
                    id="evidence-priority",
                    document_id="document-priority",
                    chunk_id="chunk-priority",
                    quote="主体曾游旧址，见于文献甲、文献乙。",
                    source_level="A",
                    review_status="reviewed",
                ),
                *[
                    WuEntityEvidenceRow(entity_id=entity_id, evidence_id="evidence-priority")
                    for entity_id in ("entity-root", "entity-doc-a", "entity-doc-b", "entity-place")
                ],
            ]
        )
        session.add_all(
            [
                WuRelationRow(
                    id="a-document-a",
                    subject_id="entity-root",
                    relation_type="documented_in",
                    object_id="entity-doc-a",
                    confidence=1,
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                WuRelationRow(
                    id="b-document-b",
                    subject_id="entity-root",
                    relation_type="documented_in",
                    object_id="entity-doc-b",
                    confidence=1,
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                WuRelationRow(
                    id="z-substantive-place",
                    subject_id="entity-root",
                    relation_type="visited",
                    object_id="entity-place",
                    confidence=1,
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.add_all(
            WuRelationEvidenceRow(relation_id=relation_id, evidence_id="evidence-priority")
            for relation_id in ("a-document-a", "b-document-b", "z-substantive-place")
        )
        await session.commit()

    try:
        result = await PersistentGraphQueryService(SqlKnowledgeGraphRepository(factory)).query(
            entity="主体", max_depth=1, max_nodes=3
        )

        assert result["status"] == "supported"
        assert "entity-place" in {node["id"] for node in result["nodes"]}
        assert "z-substantive-place" in {edge["id"] for edge in result["edges"]}

        wide_result = await PersistentGraphQueryService(
            SqlKnowledgeGraphRepository(factory)
        ).query(entity="主体", max_depth=1, max_nodes=10)
        assert {node["id"] for node in wide_result["nodes"]} == {
            "entity-root",
            "entity-place",
        }
        assert all(edge["relation_type"] != "documented_in" for edge in wide_result["edges"])
    finally:
        await engine.dispose()


def test_migration_0029_adds_graph_relation_tables(tmp_path) -> None:
    asyncio.run(_run_migration(tmp_path))


async def _run_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0028_operations_loop")
        await asyncio.to_thread(_upgrade, config, "0029_knowledge_graph_relations")
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()
        assert version == "0029_knowledge_graph_relations"
        assert {"wu_relations", "wu_relation_evidence"} <= tables
    finally:
        await engine.dispose()
