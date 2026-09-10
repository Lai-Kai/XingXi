from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from wu_culture.entities import (
    EntityCreate,
    EntityInUseError,
    EntityService,
    EntityValidationError,
    InMemoryEntityRepository,
)
from wu_culture.models import EntityType, ReviewStatus

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_create_different_types_and_same_names_allowed() -> None:
    async def _run() -> None:
        repo = InMemoryEntityRepository()
        service = EntityService(repo)
        bridge = await service.create(
            EntityCreate(
                id="entity-bridge-1",
                canonical_name="普济桥",
                entity_type=EntityType.BRIDGE,
                dynasty="qing",
                summary="香溪古桥",
                review_status=ReviewStatus.PENDING,
            )
        )
        person = await service.create(
            EntityCreate(
                id="entity-person-1",
                canonical_name="普济桥",
                entity_type=EntityType.PERSON,
                summary="同名人物不强制唯一",
            )
        )
        assert bridge.canonical_name == person.canonical_name
        assert bridge.entity_type is EntityType.BRIDGE
        listed = await service.list_entities(q="普济")
        assert len(listed) == 2

    asyncio.run(_run())


def test_list_entities_accepts_release_scope() -> None:
    async def _run() -> None:
        repo = InMemoryEntityRepository()
        service = EntityService(repo)
        await service.create(
            EntityCreate(
                id="entity-release-scoped",
                canonical_name="release-scoped",
                entity_type=EntityType.PLACE,
            )
        )

        listed = await service.list_entities(release_id="release-1")

        assert [item.id for item in listed] == ["entity-release-scoped"]

    asyncio.run(_run())


def test_reviewed_requires_evidence_and_detail_includes_sources() -> None:
    async def _run() -> None:
        repo = InMemoryEntityRepository()
        repo.put_evidence(
            "ev-1",
            {
                "evidence_id": "ev-1",
                "document_id": "doc-1",
                "quote": "香溪有普济桥",
                "source_level": "A",
                "review_status": "reviewed",
            },
        )
        service = EntityService(repo)
        with pytest.raises(EntityValidationError):
            await service.create(
                EntityCreate(
                    canonical_name="普济桥",
                    entity_type=EntityType.BRIDGE,
                    review_status=ReviewStatus.REVIEWED,
                )
            )
        created = await service.create(
            EntityCreate(
                id="entity-bridge-2",
                canonical_name="普济桥",
                entity_type=EntityType.BRIDGE,
                review_status=ReviewStatus.REVIEWED,
                evidence_ids=("ev-1",),
            )
        )
        detail = await service.get_detail(created.id)
        assert detail is not None
        assert detail.evidence[0]["evidence_id"] == "ev-1"

    asyncio.run(_run())


def test_entity_evidence_ids_must_exist_and_be_unique() -> None:
    async def _run() -> None:
        repo = InMemoryEntityRepository()
        repo.put_evidence("ev-1", {"evidence_id": "ev-1", "quote": "香溪有桥"})
        service = EntityService(repo)

        with pytest.raises(EntityValidationError, match="unknown evidence_id"):
            await service.create(
                EntityCreate(
                    canonical_name="甲桥",
                    entity_type=EntityType.BRIDGE,
                    evidence_ids=("missing",),
                )
            )
        with pytest.raises(EntityValidationError, match="must be unique"):
            await service.create(
                EntityCreate(
                    canonical_name="甲桥",
                    entity_type=EntityType.BRIDGE,
                    evidence_ids=("ev-1", "ev-1"),
                )
            )

    asyncio.run(_run())


def test_delete_protected_when_referenced() -> None:
    async def _run() -> None:
        repo = InMemoryEntityRepository()
        service = EntityService(repo)
        entity = await service.create(
            EntityCreate(id="entity-x", canonical_name="甲桥", entity_type=EntityType.BRIDGE)
        )
        repo.set_relation_refs(entity.id, 1)
        with pytest.raises(EntityInUseError):
            await service.delete(entity.id)
        await service.delete(entity.id, force=True)
        assert await service.get_detail(entity.id) is None

    asyncio.run(_run())


def test_migration_0023_entities(tmp_path) -> None:
    asyncio.run(_migration(tmp_path))


async def _migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'entities.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0022_alias_query_expansion")
        await asyncio.to_thread(_upgrade, config, "0023_entities")
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()
        assert version == "0023_entities"
        assert {"wu_entities", "wu_entity_evidence"} <= tables
    finally:
        await engine.dispose()
