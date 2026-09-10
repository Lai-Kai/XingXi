from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_0038_adds_persisted_map_snapshot_body(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'map-snapshot-body.db'}"
    )
    try:
        await asyncio.to_thread(
            _upgrade,
            _get_alembic_config(engine),
            "0037_release_preparation_state",
        )
        await asyncio.to_thread(
            _upgrade,
            _get_alembic_config(engine),
            "0038_map_asset_snapshot_body",
        )
        async with engine.connect() as connection:
            columns = {
                column["name"]
                for column in await connection.run_sync(
                    lambda sync: sa.inspect(sync).get_columns("wu_asset_versions")
                )
            }
            version = (
                await connection.execute(sa.text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
        assert "map_manifest_json" in columns
        assert version == "0038_map_asset_snapshot_body"
    finally:
        await engine.dispose()
