from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway.routers.operations import OperationEventCreate
from deerflow.persistence.operations import OperationsRepository


def test_operation_event_key_is_idempotent() -> None:
    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                CREATE TABLE wu_operation_events (
                    id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
                    event_key TEXT UNIQUE, user_id TEXT, thread_id TEXT,
                    run_id TEXT, release_id TEXT, entity_id TEXT,
                    entity_name TEXT, citation_count INTEGER,
                    is_accurate BOOLEAN, refused BOOLEAN,
                    refusal_compliant BOOLEAN, metadata_json TEXT NOT NULL,
                    occurred_at DATETIME NOT NULL
                )
                """),
            )
        repository = OperationsRepository(async_sessionmaker(engine, expire_on_commit=False))
        body = OperationEventCreate(
            event_type="answer_completed",
            event_key="answer:run-1:message-1",
            run_id="run-1",
            citation_count=2,
        )

        first = await repository.record_event(body, user_id="user-1")
        second = await repository.record_event(body, user_id="user-1")
        async with engine.connect() as connection:
            count = (await connection.execute(text("SELECT COUNT(*) FROM wu_operation_events"))).scalar_one()
        await engine.dispose()

        assert first["id"] == second["id"]
        assert count == 1

    asyncio.run(scenario())


def test_asset_snapshot_does_not_turn_entity_query_failure_into_empty_snapshot() -> None:
    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """CREATE TABLE wu_asset_versions (
                    id TEXT PRIMARY KEY,
                    knowledge_release_id TEXT UNIQUE NOT NULL,
                    knowledge_release_version TEXT NOT NULL,
                    graph_manifest_sha256 TEXT NOT NULL,
                    map_manifest_sha256 TEXT NOT NULL,
                    map_manifest_json TEXT,
                    entity_count INTEGER NOT NULL,
                        map_point_count INTEGER NOT NULL,
                        created_by TEXT NOT NULL,
                        created_at DATETIME NOT NULL
                    )"""
                )
            )
        repository = OperationsRepository(
            async_sessionmaker(engine, expire_on_commit=False)
        )
        with pytest.raises(OperationalError):
            await repository.ensure_asset_snapshot(
                release_id="release-1",
                release_version="v1",
                map_manifest={"points": []},
                actor_id="admin-1",
            )
        async with engine.connect() as connection:
            count = (
                await connection.execute(text("SELECT COUNT(*) FROM wu_asset_versions"))
            ).scalar_one()
        await engine.dispose()
        assert count == 0

    asyncio.run(scenario())


def test_asset_snapshot_persists_map_body_and_hash() -> None:
    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """CREATE TABLE wu_entities (
                        id TEXT PRIMARY KEY,
                        canonical_name TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        review_status TEXT NOT NULL,
                        release_id TEXT
                    )"""
                )
            )
            await connection.execute(
                text(
                    """CREATE TABLE wu_asset_versions (
                        id TEXT PRIMARY KEY,
                        knowledge_release_id TEXT UNIQUE NOT NULL,
                        knowledge_release_version TEXT NOT NULL,
                        graph_manifest_sha256 TEXT NOT NULL,
                        map_manifest_sha256 TEXT NOT NULL,
                        map_manifest_json TEXT,
                        entity_count INTEGER NOT NULL,
                        map_point_count INTEGER NOT NULL,
                        created_by TEXT NOT NULL,
                        created_at DATETIME NOT NULL
                    )"""
                )
            )
        repository = OperationsRepository(
            async_sessionmaker(engine, expire_on_commit=False)
        )
        manifest = {"points": [{"id": "point-1"}], "routes": []}
        snapshot = await repository.ensure_asset_snapshot(
            release_id="release-1",
            release_version="v1",
            map_manifest=manifest,
            actor_id="admin-1",
        )
        assert snapshot["map_manifest_json"] == '{"points":[{"id":"point-1"}],"routes":[]}'
        assert snapshot["map_point_count"] == 1
        async with repository._sf() as session:
            await repository.ensure_release_ready(
                session,
                # The method only needs the release ID for this assertion.
                type("Release", (), {"id": "release-1"})(),
            )
        await engine.dispose()

    asyncio.run(scenario())
