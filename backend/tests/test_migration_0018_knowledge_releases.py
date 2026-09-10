from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_immutable_release_manifest_and_active_state(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'release-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0017_text_review")
        await asyncio.to_thread(_upgrade, config, "0018_knowledge_releases")
        async with engine.connect() as connection:
            schema = await connection.run_sync(_inspect_schema)
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()
            state = (await connection.execute(sa.text("SELECT active_release_id, state_version FROM wu_knowledge_release_state WHERE id='active'"))).one()

        assert version == "0018_knowledge_releases"
        assert schema["tables"] >= {
            "wu_knowledge_releases",
            "wu_knowledge_release_items",
            "wu_knowledge_release_state",
            "wu_knowledge_release_events",
        }
        assert {tuple(item["column_names"]) for item in schema["release_uniques"]} == {("manifest_sha256",), ("version_number",)}
        assert {tuple(item["column_names"]) for item in schema["item_uniques"]} == {("release_id", "chunk_id")}
        assert state == (None, 0)
    finally:
        await engine.dispose()


def _inspect_schema(connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "tables": set(inspector.get_table_names()),
        "release_uniques": inspector.get_unique_constraints("wu_knowledge_releases"),
        "item_uniques": inspector.get_unique_constraints("wu_knowledge_release_items"),
    }
