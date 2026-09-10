from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_0042_runs_on_sqlite(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'prune-unbacked-graph.db'}"
    )
    try:
        await asyncio.to_thread(
            _upgrade,
            _get_alembic_config(engine),
            "0041_remove_placeholder_entities",
        )
        await asyncio.to_thread(
            _upgrade,
            _get_alembic_config(engine),
            "0042_prune_unbacked_graph",
        )
    finally:
        await engine.dispose()
