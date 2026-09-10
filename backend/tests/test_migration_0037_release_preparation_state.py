from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_0037_classifies_complete_and_incomplete_legacy_releases(tmp_path) -> None:
    asyncio.run(_exercise_complete_active_release(tmp_path))


def test_migration_0037_clears_incomplete_legacy_active_pointer(tmp_path) -> None:
    asyncio.run(_exercise_incomplete_active_release(tmp_path))


async def _exercise_complete_active_release(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'release-state-complete.db'}"
    )
    try:
        await _upgrade_to_0036(engine)
        async with engine.begin() as connection:
            await _insert_release(connection, "release-complete", 1, "a" * 64)
            await _insert_release(connection, "release-incomplete", 2, "b" * 64)
            await connection.execute(
                sa.text(
                    """INSERT INTO wu_fulltext_index_states
                    (release_id,manifest_sha256,document_count,status,indexed_at)
                    VALUES ('release-complete',:manifest,1,'ready',CURRENT_TIMESTAMP)"""
                ),
                {"manifest": "a" * 64},
            )
            await connection.execute(
                sa.text(
                    """INSERT INTO wu_asset_versions
                    (id,knowledge_release_id,knowledge_release_version,
                     graph_manifest_sha256,map_manifest_sha256,entity_count,
                     map_point_count,created_by,created_at)
                    VALUES ('asset-complete','release-complete','v1',:graph_hash,
                            :map_hash,0,0,'admin-1',CURRENT_TIMESTAMP)"""
                ),
                {"graph_hash": "c" * 64, "map_hash": "d" * 64},
            )
            await connection.execute(
                sa.text(
                    """UPDATE wu_knowledge_release_state
                    SET active_release_id='release-complete',state_version=5,
                        updated_by='admin-1',updated_at=CURRENT_TIMESTAMP
                    WHERE id='active'"""
                )
            )

        await asyncio.to_thread(
            _upgrade,
            _get_alembic_config(engine),
            "0037_release_preparation_state",
        )
        async with engine.connect() as connection:
            releases = {
                row.id: row
                for row in (
                    await connection.execute(
                        sa.text(
                            """SELECT id,status,failure_code,ready_at,activated_at
                            FROM wu_knowledge_releases ORDER BY version_number"""
                        )
                    )
                ).mappings()
            }
            state = (
                await connection.execute(
                    sa.text(
                        """SELECT active_release_id,state_version
                        FROM wu_knowledge_release_state WHERE id='active'"""
                    )
                )
            ).mappings().one()
            version = (
                await connection.execute(sa.text("SELECT version_num FROM alembic_version"))
            ).scalar_one()

        assert version == "0037_release_preparation_state"
        assert releases["release-complete"]["status"] == "active"
        assert releases["release-complete"]["ready_at"] is not None
        assert releases["release-complete"]["activated_at"] is not None
        assert releases["release-incomplete"]["status"] == "failed"
        assert (
            releases["release-incomplete"]["failure_code"]
            == "legacy_assets_incomplete"
        )
        assert state == {"active_release_id": "release-complete", "state_version": 5}
    finally:
        await engine.dispose()


async def _exercise_incomplete_active_release(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'release-state-incomplete.db'}"
    )
    try:
        await _upgrade_to_0036(engine)
        async with engine.begin() as connection:
            await _insert_release(connection, "release-incomplete", 1, "e" * 64)
            await connection.execute(
                sa.text(
                    """UPDATE wu_knowledge_release_state
                    SET active_release_id='release-incomplete',state_version=5,
                        updated_by='admin-1',updated_at=CURRENT_TIMESTAMP
                    WHERE id='active'"""
                )
            )

        await asyncio.to_thread(
            _upgrade,
            _get_alembic_config(engine),
            "0037_release_preparation_state",
        )
        async with engine.connect() as connection:
            release = (
                await connection.execute(
                    sa.text(
                        """SELECT status,failure_code
                        FROM wu_knowledge_releases WHERE id='release-incomplete'"""
                    )
                )
            ).mappings().one()
            state = (
                await connection.execute(
                    sa.text(
                        """SELECT active_release_id,state_version
                        FROM wu_knowledge_release_state WHERE id='active'"""
                    )
                )
            ).mappings().one()

        assert release == {
            "status": "failed",
            "failure_code": "legacy_assets_incomplete",
        }
        assert state == {"active_release_id": None, "state_version": 6}
    finally:
        await engine.dispose()


async def _upgrade_to_0036(engine) -> None:  # noqa: ANN001
    await asyncio.to_thread(
        _upgrade,
        _get_alembic_config(engine),
        "0036_ingestion_fk_compatibility",
    )


async def _insert_release(connection, release_id: str, version: int, manifest: str) -> None:  # noqa: ANN001
    await connection.execute(
        sa.text(
            """INSERT INTO wu_knowledge_releases
            (id,version_number,release_notes,scope,manifest_sha256,created_by,created_at)
            VALUES (:id,:version_number,:notes,'public',:manifest,'admin-1',CURRENT_TIMESTAMP)"""
        ),
        {
            "id": release_id,
            "version_number": version,
            "notes": f"legacy release {version}",
            "manifest": manifest,
        },
    )
