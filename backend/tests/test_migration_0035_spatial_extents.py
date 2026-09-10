from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_0035_backfills_non_exact_locations_as_extents(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0034_internal_working_releases")
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO wu_geo_features "
                    "(entity_id, name, longitude, latitude, confidence, basis, "
                    "review_status, release_id, created_at, updated_at) VALUES "
                    "('approximate-place', '近似地点', 120.5, 31.2, 'approximate', "
                    "'test', 'reviewed', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                    "('speculative-place', '推测地点', 120.6, 31.3, 'speculative', "
                    "'test', 'reviewed', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )

        await asyncio.to_thread(_upgrade, config, "0035_spatial_extents")
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    sa.text(
                        "SELECT confidence, geometry_type, uncertainty_radius_m, "
                        "extent_source, extent_basis FROM wu_geo_features "
                        "ORDER BY confidence"
                    )
                )
            ).mappings().all()
            version = (
                await connection.execute(sa.text("SELECT version_num FROM alembic_version"))
            ).scalar_one()

        assert version == "0035_spatial_extents"
        assert [(row["confidence"], row["uncertainty_radius_m"]) for row in rows] == [
            ("approximate", 750.0),
            ("speculative", 2500.0),
        ]
        assert {row["geometry_type"] for row in rows} == {"uncertainty_radius"}
        assert {row["extent_source"] for row in rows} == {"confidence_default"}
        assert all("不代表历史边界或统计概率" in row["extent_basis"] for row in rows)
    finally:
        await engine.dispose()
