from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test_text_review_sql_repository import _seed_review_targets

from app.gateway.routers.research_feed import SqlResearchFeedCandidateRepository
from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture.model import (
    WU_CULTURE_TABLES,
    EvidenceRow,
    KnowledgeReleaseItemRow,
    KnowledgeReleaseRow,
    WuEntityEvidenceRow,
    WuEntityRow,
)


@pytest.mark.asyncio
async def test_topic_seeds_include_evidence_bound_entities_with_no_release_id(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'research-feed.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[ObjectMetadataRow.__table__, *WU_CULTURE_TABLES],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 8, 25, tzinfo=UTC)

    await _seed_review_targets(factory)
    async with factory() as session:
        session.add(
            KnowledgeReleaseRow(
                id="release-current",
                version_number=7,
                release_notes="测试发布",
                scope="public",
                status="active",
                manifest_sha256="a" * 64,
                created_by="admin-1",
                created_at=now,
            )
        )
        session.add(
            KnowledgeReleaseItemRow(
                release_id="release-current",
                ordinal=0,
                document_id="document-1",
                source_file_id="file-1",
                chunk_set_id="chunk-set-1",
                chunk_id="chunk-1",
                content_sha256="b" * 64,
                cleaned_page_ids_json="[]",
            )
        )
        session.add(
            EvidenceRow(
                id="evidence-mudu",
                document_id="document-1",
                chunk_id="chunk-1",
                quote="木渎有桥。",
                source_level="A",
                review_status="reviewed",
            )
        )
        session.add(
            WuEntityRow(
                id="entity-mudu",
                canonical_name="木渎",
                entity_type="place",
                summary="资料中的地点",
                review_status="pending",
                release_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            WuEntityEvidenceRow(
                entity_id="entity-mudu",
                evidence_id="evidence-mudu",
            )
        )
        await session.commit()

    try:
        seeds = await SqlResearchFeedCandidateRepository(factory).list_release_topic_seeds(
            "release-current",
            limit=10,
        )

        assert any(seed.subject == "木渎" and seed.subject_type == "place" for seed in seeds)
    finally:
        await engine.dispose()
