from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from wu_culture import EntityType, ReviewStatus
from wu_culture.aliases import AliasExpansionRequest, AliasIndexError, AliasRecord, AliasType, AsyncAliasExpansionService
from wu_culture.filters import Dynasty

from deerflow.persistence.base import Base
from deerflow.persistence.object_storage import ObjectMetadataRow
from deerflow.persistence.wu_culture import (
    AliasDynastyRow,
    AliasEvidenceRow,
    AliasIndexRow,
    ChunkSetRow,
    EvidenceRow,
    KnowledgeReleaseRow,
    SourceDocumentRow,
    SourceFileRow,
    SqlAliasRepository,
    TextChunkRow,
)

NOW = datetime(2026, 7, 21, 23, 30, tzinfo=UTC)


def test_sql_alias_index_preserves_evidence_dynasty_and_ambiguity(tmp_path) -> None:
    asyncio.run(_exercise_repository(tmp_path))


async def _exercise_repository(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'aliases.db'}")
    tables = [
        SourceDocumentRow.__table__,
        ObjectMetadataRow.__table__,
        SourceFileRow.__table__,
        ChunkSetRow.__table__,
        TextChunkRow.__table__,
        EvidenceRow.__table__,
        KnowledgeReleaseRow.__table__,
        AliasIndexRow.__table__,
        AliasDynastyRow.__table__,
        AliasEvidenceRow.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            SourceDocumentRow(
                id="document-1",
                title="木渎小志",
                source_type="gazetteer",
                source_level="A",
                copyright_status="public_domain",
                source_institution="test",
                holder="test",
                status="registered",
                authorization_status="active",
                authorization_basis="test",
                visibility_scope="public",
                authorized_uses_json='["public_quote"]',
            )
        )
        session.add(
            TextChunkRow(
                id="chunk-1",
                document_id="document-1",
                split_version="v1",
                chunk_index=0,
                original_text="香溪古桥",
                normalized_text="香溪古桥",
                page_start=1,
                page_end=1,
                review_status="reviewed",
            )
        )
        session.add(EvidenceRow(id="evidence-1", document_id="document-1", chunk_id="chunk-1", quote="香溪古桥", source_level="A", review_status="reviewed"))
        session.add(KnowledgeReleaseRow(id="release-1", version_number=1, release_notes="test", manifest_sha256="a" * 64, created_by="admin", created_at=NOW))
        await session.commit()

    repository = SqlAliasRepository(session_factory)
    records = (
        _record("alias-1", "entity-river", "香溪河"),
        _record("alias-2", "entity-village", "香溪村"),
    )
    try:
        await repository.replace_release("release-1", records)
        stored = await repository.list_matching("release-1", "香溪有哪些古桥")
        assert [record.id for record in stored] == ["alias-1", "alias-2"]
        assert stored[0].applicable_dynasties == (Dynasty.QING,)
        assert stored[0].evidence_ids == ("evidence-1",)

        expansion = await AsyncAliasExpansionService(repository).expand(AliasExpansionRequest(query="香溪有哪些古桥", release_id="release-1"))
        assert expansion.requires_disambiguation is True
        assert expansion.resolved_query is None

        broken = _record("alias-broken", "entity-broken", "错误实体").model_copy(update={"evidence_ids": ("missing-evidence",)})
        with pytest.raises(AliasIndexError, match="was not found"):
            await repository.replace_release("release-1", (broken,))
        assert len(await repository.list_matching("release-1", "香溪")) == 2
    finally:
        await engine.dispose()


def _record(alias_id: str, entity_id: str, canonical_name: str) -> AliasRecord:
    return AliasRecord(
        id=alias_id,
        release_id="release-1",
        entity_id=entity_id,
        canonical_name=canonical_name,
        entity_type=EntityType.PLACE,
        alias="香溪",
        alias_type=AliasType.HISTORICAL_NAME,
        applicable_dynasties=(Dynasty.QING,),
        evidence_ids=("evidence-1",),
        review_status=ReviewStatus.REVIEWED,
        indexed_at=NOW,
    )
