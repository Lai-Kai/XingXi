from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture.events import EventCreate, TimeCertainty
from wu_culture.geo import (
    GeoFeature,
    SpatialConfidence,
    SpatialExtentSource,
    SpatialGeometryType,
)

from deerflow.agents.xingxi.tools import build_query_map_features_tool, build_query_timeline_tool
from deerflow.persistence.base import Base
from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade
from deerflow.persistence.wu_culture.model import WU_CULTURE_TABLES, WuEntityRow
from deerflow.persistence.wu_culture.temporal_repository import SqlEventRepository, SqlGeoRepository


@pytest.mark.asyncio
async def test_inferred_event_and_speculative_location_work_without_documents(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'temporal.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=WU_CULTURE_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all(
            [
                WuEntityRow(
                    id="person-1",
                    canonical_name="Sample Person",
                    entity_type="person",
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                WuEntityRow(
                    id="place-1",
                    canonical_name="Sample Place",
                    entity_type="place",
                    review_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    try:
        events = SqlEventRepository(factory)
        created = await events.create(
            EventCreate(
                id="event-1",
                title="Sample visit",
                event_type="visit",
                start_time="1900",
                time_certainty=TimeCertainty.APPROXIMATE,
                place_entity_id="place-1",
                participant_entity_ids=("person-1",),
                summary="Demonstration data, not a historical claim.",
                is_inferred=True,
            )
        )
        await SqlGeoRepository(factory).upsert(
            GeoFeature(
                entity_id="place-1",
                name="Sample Place",
                lon=120.5,
                lat=31.2,
                confidence=SpatialConfidence.SPECULATIVE,
                basis="Demonstration coordinate only.",
                geometry_type=SpatialGeometryType.HISTORICAL_AREA,
                area_coordinates=(
                    (120.49, 31.19),
                    (120.51, 31.19),
                    (120.51, 31.21),
                    (120.49, 31.21),
                    (120.49, 31.19),
                ),
                extent_source=SpatialExtentSource.EDITORIAL_ESTIMATE,
                extent_basis="Approximate historical area for demonstration.",
            )
        )

        stored_events = await SqlEventRepository(factory).list(participant_entity_id="person-1")
        stored_geo = await SqlGeoRepository(factory).list(entity_ids=("place-1",))
        timeline_result = await build_query_timeline_tool(SqlEventRepository(factory)).ainvoke(
            {"entity_id": "person-1"}
        )
        map_result = await build_query_map_features_tool(SqlGeoRepository(factory)).ainvoke(
            {"entity_ids": ["place-1"]}
        )

        assert stored_events == [created]
        assert stored_events[0].is_inferred is True
        assert stored_events[0].evidence_ids == ()
        assert stored_geo[0].confidence is SpatialConfidence.SPECULATIVE
        assert stored_geo[0].basis == "Demonstration coordinate only."
        assert stored_geo[0].geometry_type is SpatialGeometryType.HISTORICAL_AREA
        assert len(stored_geo[0].area_coordinates) == 5
        assert stored_geo[0].extent_source is SpatialExtentSource.EDITORIAL_ESTIMATE
        assert timeline_result["status"] == "supported"
        assert timeline_result["events"][0]["id"] == "event-1"
        assert map_result["status"] == "supported"
        assert map_result["features"][0]["entity_id"] == "place-1"
    finally:
        await engine.dispose()


def test_legacy_non_exact_location_becomes_an_explicit_uncertainty_area() -> None:
    feature = GeoFeature(
        entity_id="place-legacy",
        name="Legacy place",
        lon=120.5,
        lat=31.2,
        confidence=SpatialConfidence.APPROXIMATE,
        basis="Legacy centre point.",
    )

    assert feature.geometry_type is SpatialGeometryType.UNCERTAINTY_RADIUS
    assert feature.uncertainty_radius_m == 750
    assert feature.extent_source is SpatialExtentSource.CONFIDENCE_DEFAULT
    assert "不代表历史边界或统计概率" in feature.extent_basis


def test_migration_0030_adds_event_and_geo_tables(tmp_path) -> None:
    asyncio.run(_run_migration(tmp_path))


def test_migration_0035_backfills_non_exact_points_as_uncertainty_areas(tmp_path) -> None:
    asyncio.run(_run_spatial_extent_migration(tmp_path))


async def _run_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0029_knowledge_graph_relations")
        await asyncio.to_thread(_upgrade, config, "0030_events_geo")
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()
        assert version == "0030_events_geo"
        assert {
            "wu_historical_events",
            "wu_event_participants",
            "wu_event_evidence",
            "wu_geo_features",
            "wu_geo_evidence",
        } <= tables
    finally:
        await engine.dispose()


async def _run_spatial_extent_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'spatial-extent.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0034_internal_working_releases")
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO wu_entities "
                    "(id, canonical_name, entity_type, review_status, created_at, updated_at) "
                    "VALUES ('place-legacy', 'Legacy place', 'place', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            await connection.execute(
                sa.text(
                    "INSERT INTO wu_geo_features "
                    "(entity_id, name, longitude, latitude, confidence, basis, review_status, created_at, updated_at) "
                    "VALUES ('place-legacy', 'Legacy place', 120.5, 31.2, 'speculative', "
                    "'Legacy point', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
        await asyncio.to_thread(_upgrade, config, "0035_spatial_extents")
        async with engine.connect() as connection:
            columns = {
                column["name"]
                for column in await connection.run_sync(
                    lambda sync: sa.inspect(sync).get_columns("wu_geo_features")
                )
            }
            row = (
                await connection.execute(
                    sa.text(
                        "SELECT geometry_type, uncertainty_radius_m, extent_source "
                        "FROM wu_geo_features WHERE entity_id = 'place-legacy'"
                    )
                )
            ).one()
        assert {
            "geometry_type",
            "uncertainty_radius_m",
            "area_coordinates_json",
            "extent_source",
            "extent_basis",
        } <= columns
        assert tuple(row) == ("uncertainty_radius", 2500.0, "confidence_default")
    finally:
        await engine.dispose()
