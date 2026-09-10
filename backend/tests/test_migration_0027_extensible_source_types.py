from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_custom_source_type_label(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(database_url)
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0026_feedback_quality")
        await asyncio.to_thread(_upgrade, config, "head")
        async with engine.connect() as connection:
            columns = await connection.run_sync(
                lambda sync: {column["name"] for column in sa.inspect(sync).get_columns("wu_source_documents")}
            )
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()
        assert "source_type_label" in columns
        assert version == "0027_extensible_source_types"
    finally:
        await engine.dispose()
