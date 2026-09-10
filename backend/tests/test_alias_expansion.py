from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from wu_culture import Citation, EntityType, ReviewStatus, SearchStatus, SourceLevel
from wu_culture.aliases import (
    AliasExpansionRequest,
    AliasExpansionService,
    AliasRecord,
    AliasType,
    AsyncAliasExpansionService,
    InMemoryAliasRepository,
)
from wu_culture.filters import Dynasty
from wu_culture.hybrid import HybridChannel, HybridChannelReport, HybridChannelStatus, HybridSearchHit, HybridSearchResponse
from wu_culture.structured_search import StructuredSearchRequest, StructuredSearchService

NOW = datetime(2026, 7, 21, 23, 0, tzinfo=UTC)


def _alias(
    alias_id: str,
    *,
    entity_id: str,
    canonical_name: str,
    alias: str,
    dynasties=(Dynasty.QING,),
    evidence_ids=("evidence-1",),
    review_status=ReviewStatus.REVIEWED,
) -> AliasRecord:
    return AliasRecord(
        id=alias_id,
        release_id="release-1",
        entity_id=entity_id,
        canonical_name=canonical_name,
        entity_type=EntityType.PLACE,
        alias=alias,
        alias_type=AliasType.HISTORICAL_NAME,
        applicable_dynasties=dynasties,
        evidence_ids=evidence_ids,
        review_status=review_status,
        indexed_at=NOW,
    )


def test_evidence_backed_old_name_expands_but_standard_name_is_left_unchanged() -> None:
    service = AliasExpansionService(InMemoryAliasRepository((_alias("alias-1", entity_id="entity-mudu", canonical_name="木渎", alias="木瀆"),)))

    expanded = service.expand(AliasExpansionRequest(query="木瀆有哪些古桥", release_id="release-1"))
    standard = service.expand(AliasExpansionRequest(query="木渎有哪些古桥", release_id="release-1"))

    assert expanded.resolved_query == "木渎有哪些古桥"
    assert expanded.expanded_terms == ("木渎",)
    assert expanded.candidates[0].eligible is True
    assert expanded.candidates[0].evidence_ids == ("evidence-1",)
    assert standard.resolved_query == standard.original_query
    assert standard.candidates == ()


def test_same_alias_for_different_entities_requires_disambiguation() -> None:
    repository = InMemoryAliasRepository(
        (
            _alias("alias-1", entity_id="entity-place", canonical_name="香溪河", alias="香溪"),
            _alias("alias-2", entity_id="entity-village", canonical_name="香溪村", alias="香溪"),
        )
    )
    result = AliasExpansionService(repository).expand(AliasExpansionRequest(query="香溪旧桥", release_id="release-1"))

    assert result.requires_disambiguation is True
    assert result.resolved_query is None
    assert {candidate.entity_id for candidate in result.candidates} == {"entity-place", "entity-village"}
    assert all(candidate.reason == "ambiguous_alias" for candidate in result.candidates)


def test_dynasty_mismatch_and_missing_or_unreviewed_evidence_never_auto_expand() -> None:
    repository = InMemoryAliasRepository(
        (
            _alias("alias-era", entity_id="entity-era", canonical_name="清代名称", alias="旧称", dynasties=(Dynasty.QING,)),
            _alias("alias-empty", entity_id="entity-empty", canonical_name="无据名称", alias="俗名", evidence_ids=()),
            _alias(
                "alias-pending",
                entity_id="entity-pending",
                canonical_name="待审名称",
                alias="异名",
                review_status=ReviewStatus.PENDING,
            ),
        )
    )
    service = AliasExpansionService(repository)

    era = service.expand(
        AliasExpansionRequest(
            query="旧称遗迹",
            release_id="release-1",
            dynasties=(Dynasty.MING,),
        )
    )
    no_evidence = service.expand(AliasExpansionRequest(query="俗名遗迹", release_id="release-1"))
    pending = service.expand(AliasExpansionRequest(query="异名遗迹", release_id="release-1"))

    assert era.resolved_query == era.original_query
    assert era.candidates[0].reason == "dynasty_mismatch"
    assert no_evidence.candidates[0].reason == "missing_evidence"
    assert pending.candidates[0].reason == "alias_not_reviewed"
    assert not era.candidates[0].eligible
    assert not no_evidence.candidates[0].eligible
    assert not pending.candidates[0].eligible


def test_expansion_limit_is_deterministic_and_reported() -> None:
    records = tuple(
        _alias(
            f"alias-{index}",
            entity_id=f"entity-{index}",
            canonical_name=f"标准名{index}",
            alias=f"旧名{index}",
        )
        for index in range(4)
    )
    result = AliasExpansionService(InMemoryAliasRepository(records)).expand(
        AliasExpansionRequest(
            query="旧名0旧名1旧名2旧名3",
            release_id="release-1",
            max_expansions=2,
        )
    )

    assert result.expanded_terms == ("标准名0", "标准名1")
    assert result.truncated is True


def test_structured_search_uses_unique_evidence_backed_expansion_and_exposes_trace() -> None:
    asyncio.run(_exercise_structured_alias_search())


async def _exercise_structured_alias_search() -> None:
    record = _alias("alias-1", entity_id="entity-mudu", canonical_name="木渎", alias="木瀆")

    class AsyncRepository:
        async def list_matching(self, release_id, query):
            return InMemoryAliasRepository((record,)).list_matching(release_id, query)

    class Hybrid:
        def __init__(self):
            self.queries = []

        async def search(self, request):
            self.queries.append(request.query)
            hits = ()
            if "木渎" in request.query:
                hits = (
                    HybridSearchHit(
                        release_id="release-1",
                        chunk_id="chunk-1",
                        fused_score=1.0,
                        channels=(HybridChannel.FULLTEXT,),
                        fulltext_rank=1,
                        fulltext_score=10.0,
                        fulltext_rrf_contribution=1.0,
                        citation=Citation(
                            evidence_id="evidence-1",
                            document_id="document-1",
                            document_title="木渎小志",
                            page_start=1,
                            page_end=1,
                            quote="木渎古桥",
                            source_level=SourceLevel.A,
                            review_status=ReviewStatus.REVIEWED,
                        ),
                    ),
                )
            return HybridSearchResponse(
                query=request.query,
                release_id="release-1",
                rrf_k=60,
                degraded=False,
                channel_reports=(
                    HybridChannelReport(channel=HybridChannel.FULLTEXT, status=HybridChannelStatus.OK if hits else HybridChannelStatus.EMPTY, hit_count=len(hits)),
                    HybridChannelReport(channel=HybridChannel.VECTOR, status=HybridChannelStatus.EMPTY),
                ),
                hits=hits,
                evidence_status=SearchStatus.SUPPORTED if hits else SearchStatus.INSUFFICIENT,
                message="已检索到可引用证据" if hits else "暂无明确方志记载",
            )

    hybrid = Hybrid()
    response = await StructuredSearchService(
        hybrid,
        AsyncAliasExpansionService(AsyncRepository()),
    ).search(StructuredSearchRequest(query="木瀆有哪些古桥"))

    assert hybrid.queries == ["木瀆有哪些古桥", "木渎有哪些古桥"]
    assert [hit.chunk_id for hit in response.hits] == ["chunk-1"]
    assert response.alias_expansion.resolved_query == "木渎有哪些古桥"
    assert response.alias_expansion.candidates[0].evidence_ids == ("evidence-1",)
