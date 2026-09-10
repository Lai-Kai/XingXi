from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


def test_migration_adds_filter_sidecars_and_backfills_fulltext_rows(tmp_path) -> None:
    asyncio.run(_exercise_migration(tmp_path))


async def _exercise_migration(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'filters-migration.db'}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0020_vector_search")
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO wu_source_documents "
                    "(id, title, source_type, source_level, copyright_status, source_institution, holder, status, authorization_status, visibility_scope, authorized_uses_json) "
                    "VALUES ('document-1', '木渎小志', 'gazetteer', 'A', 'public_domain', 'test', 'test', 'registered', 'active', 'public', '[\"public_quote\"]')"
                )
            )
            await connection.execute(
                sa.text("INSERT INTO wu_knowledge_releases (id, version_number, release_notes, manifest_sha256, created_by, created_at) VALUES ('release-1', 1, 'test', :hash, 'admin', CURRENT_TIMESTAMP)"), {"hash": "a" * 64}
            )
            await connection.execute(
                sa.text(
                    "INSERT INTO wu_fulltext_documents "
                    "(id, external_id, release_id, release_version, document_id, source_file_id, chunk_set_id, chunk_id, "
                    "document_title, edition, source_type, source_level, page_start, page_end, raw_text, clean_text, "
                    "search_title, search_headings, search_body, search_text, content_sha256, indexed_at) "
                    "VALUES (1, 'fulltext-1', 'release-1', 'v1', 'document-1', 'file-1', 'set-1', 'chunk-1', "
                    "'木渎小志', '清同治本', 'gazetteer', 'A', 1, 1, '古桥', '古桥', '木渎小志', '', '古桥', "
                    "'木渎小志 古桥', :hash, CURRENT_TIMESTAMP)"
                ),
                {"hash": "b" * 64},
            )
        await asyncio.to_thread(_upgrade, config, "0021_structured_search_filters")
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))
            version = (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one()
            metadata = (await connection.execute(sa.text("SELECT edition, source_type, source_level, review_status, spatial_confidence FROM wu_search_filter_metadata WHERE release_id = 'release-1' AND chunk_id = 'chunk-1'"))).one()

        assert version == "0021_structured_search_filters"
        assert {"wu_search_filter_metadata", "wu_search_filter_facets"} <= tables
        assert metadata == ("清同治本", "gazetteer", "A", "reviewed", None)
    finally:
        await engine.dispose()
