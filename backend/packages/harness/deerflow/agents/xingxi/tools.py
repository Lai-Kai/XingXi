from __future__ import annotations

from functools import partial
from typing import Annotated, Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field
from wu_culture import (
    AsyncEvidenceSearchService,
    AuthorizedUse,
    EvidenceSearchService,
    InMemoryEvidenceRepository,
    SearchFilters,
    SearchRequest,
    SourceLevel,
)
from wu_culture.aliases import EvidenceLookup, NameAuthorityRequest, NameAuthorityService, NameVariantInput
from wu_culture.compare import CompareSourcesRequest
from wu_culture.compare import compare_sources as compare_sources_domain
from wu_culture.conflicts import detect_conflicts
from wu_culture.evidence_pack import EvidencePackAssembler, EvidencePackConfig
from wu_culture.filters import StructuredSearchFilters
from wu_culture.fulltext import FullTextReleaseNotIndexed, FullTextRepository, FullTextSearchRequest
from wu_culture.geo import SpatialConfidence
from wu_culture.gloss import gloss_passage
from wu_culture.graph import InMemoryKnowledgeGraphRepository, KnowledgeGraphRepository, PersistentGraphQueryService
from wu_culture.hybrid import HybridSearchRequest, HybridSearchService, HybridSearchUnavailable
from wu_culture.modes import XingxiMode, resolve_mode_profile
from wu_culture.ranking import TrustReranker
from wu_culture.structured_search import StructuredSearchRequest, StructuredSearchService

from deerflow.persistence.wu_culture.repository import SqlEvidenceRepository, SqlFullTextRepository
from deerflow.tools.types import Runtime
from deerflow.utils.token_counting import count_text_tokens

_EMPTY_SEARCH_SERVICE = EvidenceSearchService(InMemoryEvidenceRepository())


def build_search_sources_tool(
    search_service: EvidenceSearchService | None = None,
    *,
    async_search_service: AsyncEvidenceSearchService | None = None,
    fulltext_repository: FullTextRepository | None = None,
    hybrid_search_service: HybridSearchService | None = None,
    structured_search_service: StructuredSearchService | None = None,
    evidence_pack_assembler: EvidencePackAssembler | None = None,
    evidence_pack_config: EvidencePackConfig | None = None,
) -> BaseTool:
    sync_service = search_service or _EMPTY_SEARCH_SERVICE
    resolved_pack_config = evidence_pack_config or EvidencePackConfig()
    if search_service is None and async_search_service is None:
        from deerflow.persistence import engine as persistence_engine

        session_factory = persistence_engine.get_session_factory()
        if session_factory is not None:
            async_search_service = AsyncEvidenceSearchService(
                SqlEvidenceRepository(session_factory),
                authorized_use=AuthorizedUse.PUBLIC_QUOTE,
            )
            fulltext_repository = fulltext_repository or SqlFullTextRepository(session_factory)
            if hybrid_search_service is None:
                from deerflow.config import get_app_config
                from deerflow.embeddings import EmbeddingService, VectorIndexService
                from deerflow.persistence.wu_culture import SqlVectorRepository

                config = get_app_config()
                resolved_pack_config = EvidencePackConfig(
                    token_budget=config.evidence_pack.token_budget,
                    max_items=config.evidence_pack.max_items,
                    max_quote_tokens=config.evidence_pack.max_quote_tokens,
                    min_quote_tokens=config.evidence_pack.min_quote_tokens,
                )
                if evidence_pack_assembler is None:
                    evidence_pack_assembler = EvidencePackAssembler(
                        token_counter=partial(
                            count_text_tokens,
                            strategy=config.evidence_pack.token_counting,
                        )
                    )
                vectors = None
                if config.embedding.enabled:
                    vector_repository = SqlVectorRepository(session_factory)
                    vectors = VectorIndexService(vector_repository, EmbeddingService(config.embedding))
                hybrid_search_service = HybridSearchService(
                    fulltext_repository,
                    vectors,
                    timeout_seconds=config.hybrid_search.channel_timeout_seconds,
                    rrf_k=config.hybrid_search.rrf_k,
                    reranker=TrustReranker(config.trust_rerank),
                )
    if hybrid_search_service is None and fulltext_repository is not None:
        hybrid_search_service = HybridSearchService(fulltext_repository, None)
    if structured_search_service is None and hybrid_search_service is not None:
        structured_search_service = StructuredSearchService(hybrid_search_service)
    evidence_pack_assembler = evidence_pack_assembler or EvidencePackAssembler()

    def pack_hits(hits, release_id: str) -> tuple[dict, list[dict], dict]:  # noqa: ANN001
        pack = evidence_pack_assembler.assemble(
            hits,
            release_id=release_id,
            config=resolved_pack_config,
        )
        packed_ids = {item.evidence_id for item in pack.items}
        trace = []
        for hit in hits:
            item = {
                "chunk_id": hit.chunk_id,
                "evidence_id": hit.citation.evidence_id,
                "included_in_evidence_pack": hit.citation.evidence_id in packed_ids,
                # Keep the locator contract without duplicating the potentially
                # long source quote; verbatim text lives in the evidence pack.
                "citation": hit.citation.model_dump(mode="json", exclude={"quote"}),
            }
            channels = getattr(hit, "channels", None)
            if channels is not None:
                item["channels"] = [channel.value for channel in channels]
            else:
                item["score"] = hit.score
                item["matched_terms"] = list(hit.matched_terms)
            trace.append(item)
        conflict_report = detect_conflicts(pack).model_dump(mode="json")
        return pack.model_dump(mode="json"), trace, conflict_report

    def search_sources(
        query: str,
        source_levels: list[Literal["A", "B", "C", "D", "E", "U"]] | None = None,
        document_ids: list[str] | None = None,
        filters: StructuredSearchFilters | None = None,
        top_k: int = 5,
        cursor: str | None = None,
        runtime: Runtime = None,
    ) -> dict:
        """Search reviewed Wu-culture and Mudu historical evidence.

        Call this before making factual historical claims. Every returned hit
        contains stable document, volume, section, and page locators; verbatim
        source text is returned in the evidence pack.
        Treat an insufficient response as "暂无明确方志记载" rather than evidence
        that an event or object never existed.

        Args:
            query: Historical person, place, event, object, or source passage to find.
            source_levels: Optional authority levels to include, from A through E.
            document_ids: Optional source document IDs to search within.
            top_k: Maximum number of evidence hits, between 1 and 20.
        """
        del runtime  # Declares ToolRuntime injection for StructuredTool's primary function.
        cursor = cursor.strip() or None if isinstance(cursor, str) else cursor
        if cursor is not None:
            raise ValueError("cursor pagination requires the SQL search runtime")
        if filters is not None:
            unsupported = filters.model_copy(
                update={
                    "document_ids": None,
                    "source_levels": None,
                    "source_types": None,
                }
            )
            if not unsupported.is_empty:
                raise ValueError("edition, dynasty, entity, review, and spatial filters require the SQL search runtime")
            if document_ids and filters.document_ids:
                raise ValueError("document_ids must be supplied either directly or in filters, not both")
            if source_levels and filters.source_levels:
                raise ValueError("source_levels must be supplied either directly or in filters, not both")
        response = sync_service.search(
            SearchRequest(
                query=query,
                filters=SearchFilters(
                    document_ids=document_ids or (list(filters.document_ids) if filters and filters.document_ids else None),
                    source_levels=[SourceLevel(level) for level in source_levels] if source_levels else (list(filters.source_levels) if filters and filters.source_levels else None),
                    source_types=list(filters.source_types) if filters and filters.source_types else None,
                ),
                top_k=top_k,
            )
        )
        evidence_pack, retrieval_trace, conflict_report = pack_hits(response.hits, "unversioned")
        return {
            "query": query,
            "status": response.status.value,
            "hits": retrieval_trace,
            "evidence_pack": evidence_pack,
            "conflict_report": conflict_report,
            "message": response.message,
            "release_id": "unversioned",
        }

    async def search_sources_async(
        query: str,
        source_levels: list[Literal["A", "B", "C", "D", "E", "U"]] | None = None,
        document_ids: list[str] | None = None,
        filters: StructuredSearchFilters | None = None,
        top_k: int = 5,
        cursor: str | None = None,
        runtime: Runtime = None,
    ) -> dict:
        cursor = cursor.strip() or None if isinstance(cursor, str) else cursor
        if document_ids and filters is not None and filters.document_ids:
            raise ValueError("document_ids must be supplied either directly or in filters, not both")
        requested_document_ids = document_ids or (list(filters.document_ids) if filters is not None and filters.document_ids else None)
        effective_document_ids = _project_scoped_document_ids(runtime, requested_document_ids)
        if _project_document_ids_from_runtime(runtime) is not None and not effective_document_ids:
            return {
                "query": query,
                "status": "insufficient",
                "hits": [],
                "message": "当前研究项目中没有符合范围的文献",
                "release_id": _release_id_from_runtime(runtime) or "unknown",
            }
        request = SearchRequest(
            query=query,
            filters=SearchFilters(
                document_ids=effective_document_ids,
                source_levels=[SourceLevel(level) for level in source_levels] if source_levels else None,
            ),
            top_k=top_k,
        )
        release_id = _release_id_from_runtime(runtime)
        runtime_scope = _release_scope_from_runtime(runtime)
        database_release_id, database_scope = await _active_release_context(release_id)
        if release_id is None:
            release_id = database_release_id
        authorized_use = AuthorizedUse.INTERNAL_PROCESSING if runtime_scope == "internal" or database_scope == "internal" else AuthorizedUse.PUBLIC_QUOTE
        structured_attempted = structured_search_service is not None
        if structured_search_service is not None:
            effective_filters = filters or StructuredSearchFilters()
            updates = {}
            if effective_document_ids:
                updates["document_ids"] = tuple(effective_document_ids)
            if source_levels:
                if effective_filters.source_levels is not None:
                    raise ValueError("source_levels must be supplied either directly or in filters, not both")
                updates["source_levels"] = tuple(SourceLevel(level) for level in source_levels)
            if updates:
                effective_filters = effective_filters.model_copy(update=updates)
            try:
                structured = await structured_search_service.search(
                    StructuredSearchRequest(
                        query=query,
                        release_id=release_id,
                        authorized_use=authorized_use,
                        filters=effective_filters,
                        page_size=top_k,
                        cursor=cursor,
                        candidate_k=max(top_k, min(100, top_k * 3)),
                    )
                )
            except (FullTextReleaseNotIndexed, HybridSearchUnavailable):
                structured = None
            if structured is not None:
                evidence_pack, retrieval_trace, conflict_report = pack_hits(structured.hits, structured.release_id)
                return {
                    "query": query,
                    "status": structured.evidence_status.value,
                    "hits": retrieval_trace,
                    "evidence_pack": evidence_pack,
                    "conflict_report": conflict_report,
                    "message": structured.message,
                    "release_id": structured.release_id,
                    "degraded": structured.degraded,
                    "channels": [report.model_dump(mode="json") for report in structured.channel_reports],
                    "next_cursor": structured.next_cursor,
                    "has_more": structured.has_more,
                    "filters": structured.filters.model_dump(mode="json", exclude_none=True),
                    "alias_expansion": structured.alias_expansion.model_dump(mode="json") if structured.alias_expansion is not None else None,
                }
        if hybrid_search_service is not None and not structured_attempted:
            try:
                hybrid = await hybrid_search_service.search(
                    HybridSearchRequest(
                        query=query,
                        release_id=release_id,
                        authorized_use=authorized_use,
                        document_ids=tuple(effective_document_ids) if effective_document_ids else None,
                        source_levels=tuple(SourceLevel(level) for level in source_levels) if source_levels else None,
                        top_k=top_k,
                        candidate_k=max(top_k, min(100, top_k * 3)),
                    )
                )
                if not hybrid.hits:
                    evidence_pack, retrieval_trace, conflict_report = pack_hits(hybrid.hits, hybrid.release_id)
                    return {
                        "query": query,
                        "status": hybrid.evidence_status.value,
                        "hits": retrieval_trace,
                        "evidence_pack": evidence_pack,
                        "conflict_report": conflict_report,
                        "message": hybrid.message,
                        "release_id": hybrid.release_id,
                        "degraded": hybrid.degraded,
                        "channels": [report.model_dump(mode="json") for report in hybrid.channel_reports],
                    }
                evidence_pack, retrieval_trace, conflict_report = pack_hits(hybrid.hits, hybrid.release_id)
                return {
                    "query": query,
                    "status": hybrid.evidence_status.value,
                    "hits": retrieval_trace,
                    "evidence_pack": evidence_pack,
                    "conflict_report": conflict_report,
                    "message": hybrid.message,
                    "release_id": hybrid.release_id,
                    "degraded": hybrid.degraded,
                    "channels": [report.model_dump(mode="json") for report in hybrid.channel_reports],
                }
            except FullTextReleaseNotIndexed:
                if release_id is not None:
                    return {
                        "query": query,
                        "status": "insufficient",
                        "hits": [],
                        "message": "指定知识版本的检索索引尚未就绪",
                        "release_id": release_id,
                    }
            except HybridSearchUnavailable:
                pass
        if fulltext_repository is not None:
            try:
                fulltext = await fulltext_repository.search(
                    FullTextSearchRequest(
                        query=query,
                        release_id=release_id,
                        authorized_use=authorized_use,
                        document_ids=tuple(effective_document_ids) if effective_document_ids else None,
                        source_levels=tuple(SourceLevel(level) for level in source_levels) if source_levels else None,
                        page_size=top_k,
                    )
                )
                if not fulltext.hits:
                    evidence_pack, retrieval_trace, conflict_report = pack_hits((), fulltext.release_id)
                    return {
                        "query": query,
                        "status": "insufficient",
                        "hits": retrieval_trace,
                        "evidence_pack": evidence_pack,
                        "conflict_report": conflict_report,
                        "message": "暂无明确方志记载",
                        "release_id": fulltext.release_id,
                        "release_version": fulltext.release_version,
                    }
                evidence_pack, retrieval_trace, conflict_report = pack_hits(fulltext.hits, fulltext.release_id)
                return {
                    "query": query,
                    "status": "supported",
                    "hits": retrieval_trace,
                    "evidence_pack": evidence_pack,
                    "conflict_report": conflict_report,
                    "message": "已检索到可引用证据",
                    "release_id": fulltext.release_id,
                    "release_version": fulltext.release_version,
                }
            except FullTextReleaseNotIndexed as exc:
                if release_id is not None or "no active knowledge release" not in str(exc):
                    return {
                        "query": query,
                        "status": "insufficient",
                        "hits": [],
                        "message": "指定知识版本的全文索引尚未就绪",
                        "release_id": release_id,
                    }
        if async_search_service is not None:
            response = await async_search_service.search(request)
        else:
            response = sync_service.search(request)
        evidence_pack, retrieval_trace, conflict_report = pack_hits(response.hits, release_id or "unversioned")
        return {
            "query": query,
            "status": response.status.value,
            "hits": retrieval_trace,
            "evidence_pack": evidence_pack,
            "conflict_report": conflict_report,
            "message": response.message,
            "release_id": release_id or "unversioned",
        }

    return StructuredTool.from_function(
        func=search_sources,
        coroutine=search_sources_async,
        name="search_sources",
        description=search_sources.__doc__,
        parse_docstring=True,
    )


def _release_id_from_runtime(runtime: Runtime | None) -> str | None:
    if runtime is None:
        return None
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        value = context.get("knowledge_release_id")
        if value:
            return str(value)
    config = getattr(runtime, "config", None) or {}
    metadata = config.get("metadata") if isinstance(config, dict) else None
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("knowledge_release_id")
    return str(value) if value else None


def _release_scope_from_runtime(runtime: Runtime | None) -> str:
    if runtime is None:
        return "public"
    context = getattr(runtime, "context", None)
    if isinstance(context, dict) and context.get("knowledge_release_scope") == "internal":
        return "internal"
    config = getattr(runtime, "config", None) or {}
    metadata = config.get("metadata") if isinstance(config, dict) else None
    if not isinstance(metadata, dict):
        return "public"
    return "internal" if metadata.get("knowledge_release_scope") == "internal" else "public"


async def _active_release_context(release_id: str | None) -> tuple[str | None, str | None]:
    """Resolve the release and scope when a tool call has no run metadata."""
    from deerflow.persistence import engine as persistence_engine

    session_factory = persistence_engine.get_session_factory()
    if session_factory is None:
        return release_id, None
    from deerflow.persistence.wu_culture import SqlKnowledgeReleaseRepository

    repository = SqlKnowledgeReleaseRepository(session_factory)
    release = await repository.get(release_id) if release_id else await repository.get_active()
    if release is None:
        return release_id, None
    return release.id, release.scope


def _project_document_ids_from_runtime(runtime: Runtime | None) -> list[str] | None:
    if runtime is None:
        return None
    context = getattr(runtime, "context", None)
    if not isinstance(context, dict):
        config = getattr(runtime, "config", None) or {}
        context = config.get("context") if isinstance(config, dict) else None
    if not isinstance(context, dict) or "research_project_document_ids" not in context:
        return None
    values = context.get("research_project_document_ids")
    if not isinstance(values, (list, tuple)):
        return []
    return list(dict.fromkeys(str(value) for value in values if value))


def _project_scoped_document_ids(
    runtime: Runtime | None,
    requested_document_ids: list[str] | None,
) -> list[str] | None:
    project_document_ids = _project_document_ids_from_runtime(runtime)
    if project_document_ids is None:
        return requested_document_ids
    if requested_document_ids is None:
        return project_document_ids
    requested = set(requested_document_ids)
    return [document_id for document_id in project_document_ids if document_id in requested]


def build_compare_sources_tool(
    *,
    hybrid_search_service: HybridSearchService | None = None,
    structured_search_service: StructuredSearchService | None = None,
    evidence_pack_assembler: EvidencePackAssembler | None = None,
    evidence_pack_config: EvidencePackConfig | None = None,
) -> BaseTool:
    """Researcher-facing multi-source comparison tool."""
    assembler = evidence_pack_assembler or EvidencePackAssembler()
    pack_config = evidence_pack_config or EvidencePackConfig()

    async def compare_sources_async(
        topic: str,
        document_ids: list[str] | None = None,
        release_id: str | None = None,
        max_items_per_document: int = 3,
        runtime: Runtime = None,
    ) -> dict:
        """Compare gazetteer passages on a topic.

        Args:
            topic: Research topic or question fragment to align across sources.
            document_ids: Optional document id allow-list.
            release_id: Optional knowledge release id.
            max_items_per_document: Cap per document for side-by-side columns.
        """
        resolved_release = release_id or _release_id_from_runtime(runtime)
        effective_document_ids = _project_scoped_document_ids(runtime, document_ids)
        if _project_document_ids_from_runtime(runtime) is not None and not effective_document_ids:
            return {
                "topic": topic,
                "columns": [],
                "differences": [],
                "open_questions": ["当前研究项目中没有符合范围的文献"],
                "notes": ["项目文献范围为空"],
                "release_id": resolved_release,
            }
        request = CompareSourcesRequest(
            topic=topic,
            document_ids=tuple(effective_document_ids) if effective_document_ids else None,
            release_id=resolved_release,
            max_items_per_document=max_items_per_document,
        )
        hits = []
        if structured_search_service is not None:
            structured = await structured_search_service.search(
                StructuredSearchRequest(
                    query=topic,
                    release_id=resolved_release,
                    filters=StructuredSearchFilters(
                        document_ids=tuple(effective_document_ids) if effective_document_ids else None,
                    ),
                    page_size=max(6, max_items_per_document * 4),
                )
            )
            hits = list(structured.hits)
            if not resolved_release:
                resolved_release = structured.release_id
        elif hybrid_search_service is not None:
            top_k = max(6, min(100, max_items_per_document * 4))
            hybrid = await hybrid_search_service.search(
                HybridSearchRequest(
                    query=topic,
                    release_id=resolved_release,
                    document_ids=tuple(effective_document_ids) if effective_document_ids else None,
                    top_k=top_k,
                    candidate_k=max(top_k, min(100, top_k * 3)),
                )
            )
            hits = list(hybrid.hits)
            if not resolved_release:
                resolved_release = hybrid.release_id

        pack = assembler.assemble(hits, release_id=resolved_release or "unknown", config=pack_config)
        result = compare_sources_domain(request, pack=pack, hits=hits)
        payload = result.model_dump(mode="json")
        payload["conflict_report"] = detect_conflicts(pack).model_dump(mode="json")
        return payload

    def compare_sources(
        topic: str,
        document_ids: list[str] | None = None,
        release_id: str | None = None,
        max_items_per_document: int = 3,
    ) -> dict:
        """Sync wrapper used in unit tests without an event loop runner."""
        import asyncio

        return asyncio.get_event_loop().run_until_complete(
            compare_sources_async(
                topic=topic,
                document_ids=document_ids,
                release_id=release_id,
                max_items_per_document=max_items_per_document,
            )
        )

    return StructuredTool.from_function(
        func=compare_sources,
        coroutine=compare_sources_async,
        name="compare_sources",
        description=compare_sources_async.__doc__,
        parse_docstring=True,
    )


def build_query_knowledge_graph_tool(
    graph_repository: KnowledgeGraphRepository | None = None,
) -> BaseTool:
    async def query_knowledge_graph(
        entity: str,
        max_depth: Annotated[int, Field(ge=1, le=3)] = 2,
        max_nodes: Annotated[int, Field(ge=1, le=200)] = 50,
        relation_types: list[str] | None = None,
        runtime: Runtime = None,
    ) -> dict:
        """Query people, places, events, organizations, streets, and objects in the historical knowledge graph.

        Use this for relationship questions and graph exploration. The entity may be a stable
        entity ID or a canonical name. Empty graph results are valid and must not be presented
        as proof that the entity or relationship never existed. Evidence IDs on graph edges are
        pointers for a subsequent source lookup, not quotations by themselves.

        Args:
            entity: Stable entity ID or canonical entity name.
            max_depth: Relationship traversal depth from 1 through 3.
            max_nodes: Maximum number of returned nodes from 1 through 200.
            relation_types: Optional relation type allow-list.
        """
        repository = graph_repository
        if repository is None:
            from deerflow.persistence import engine as persistence_engine

            session_factory = persistence_engine.get_session_factory()
            if session_factory is not None:
                from deerflow.persistence.wu_culture.graph_repository import SqlKnowledgeGraphRepository

                repository = SqlKnowledgeGraphRepository(session_factory)
        repository = repository or InMemoryKnowledgeGraphRepository()
        return await PersistentGraphQueryService(repository).query(
            entity=entity,
            max_depth=max_depth,
            max_nodes=max_nodes,
            relation_types=relation_types,
            release_id=_release_id_from_runtime(runtime),
        )

    return StructuredTool.from_function(
        coroutine=query_knowledge_graph,
        name="query_knowledge_graph",
        description=query_knowledge_graph.__doc__,
        parse_docstring=True,
    )


def build_query_timeline_tool(event_repository=None) -> BaseTool:  # noqa: ANN001
    async def query_timeline(
        entity_id: str | None = None,
        place_entity_id: str | None = None,
        event_type: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 30,
        runtime: Runtime = None,
    ) -> dict:
        """Query historical events in chronological order.

        Events may be filtered by participant, place, or event type. Inferred events
        remain explicitly marked and must not be described as verified history without
        evidence. An empty result means that no matching event has been entered yet.

        Args:
            entity_id: Optional participant entity ID.
            place_entity_id: Optional place entity ID.
            event_type: Optional event type.
            limit: Maximum number of returned events.
        """
        repository = event_repository
        if repository is None:
            from deerflow.persistence import engine as persistence_engine

            session_factory = persistence_engine.get_session_factory()
            if session_factory is not None:
                from deerflow.persistence.wu_culture.temporal_repository import SqlEventRepository

                repository = SqlEventRepository(session_factory)
        if repository is None:
            events = []
        else:
            events = await repository.list(
                participant_entity_id=entity_id,
                place_entity_id=place_entity_id,
                event_type=event_type,
                release_id=_release_id_from_runtime(runtime),
                limit=limit,
            )
        return {
            "status": "supported" if events else "empty",
            "message": "Historical events found." if events else "No matching event is currently available.",
            "events": [event.model_dump(mode="json") for event in events],
        }

    return StructuredTool.from_function(
        coroutine=query_timeline,
        name="query_timeline",
        description=query_timeline.__doc__,
        parse_docstring=True,
    )


def build_query_map_features_tool(geo_repository=None) -> BaseTool:  # noqa: ANN001
    async def query_map_features(
        entity_ids: list[str] | None = None,
        min_confidence: Literal["exact", "approximate", "speculative"] | None = None,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
        runtime: Runtime = None,
    ) -> dict:
        """Query map locations with confidence, basis, and Evidence IDs.

        Args:
            entity_ids: Optional entity IDs to locate.
            min_confidence: Optional minimum spatial confidence.
            limit: Maximum number of returned locations.
        """
        repository = geo_repository
        if repository is None:
            from deerflow.persistence import engine as persistence_engine

            session_factory = persistence_engine.get_session_factory()
            if session_factory is not None:
                from deerflow.persistence.wu_culture.temporal_repository import SqlGeoRepository

                repository = SqlGeoRepository(session_factory)
        if repository is None:
            features = []
        else:
            features = await repository.list(
                entity_ids=entity_ids,
                min_confidence=SpatialConfidence(min_confidence) if min_confidence else None,
                release_id=_release_id_from_runtime(runtime),
                limit=limit,
            )
        return {
            "status": "supported" if features else "empty",
            "message": "Map locations found." if features else "No matching map location is currently available.",
            "features": [feature.model_dump(mode="json") for feature in features],
        }

    return StructuredTool.from_function(
        coroutine=query_map_features,
        name="query_map_features",
        description=query_map_features.__doc__,
        parse_docstring=True,
    )


def build_gloss_ancient_text_tool() -> BaseTool:
    def gloss_ancient_text(
        text: str,
        max_chars: Annotated[int, Field(ge=1, le=10000)] = 2000,
    ) -> dict:
        """Provide a reading aid for a classical Chinese passage while preserving the original.

        Args:
            text: Original classical Chinese passage.
            max_chars: Maximum passage length to process.
        """
        return gloss_passage(text, max_chars=max_chars).model_dump(mode="json")

    return StructuredTool.from_function(
        func=gloss_ancient_text,
        name="gloss_ancient_text",
        description=gloss_ancient_text.__doc__,
        parse_docstring=True,
    )


def build_resolve_name_variants_tool(
    evidence_repository: EvidenceLookup | None = None,
) -> BaseTool:
    async def resolve_name_variants(
        variants: Annotated[list[NameVariantInput], Field(min_length=2, max_length=20)],
        research_context: Annotated[str | None, Field(max_length=500)] = None,
    ) -> dict:
        """Select a preferred historical name using real reviewed evidence metadata.

        Use this after source search finds different names for the same object.
        The tool preserves every variant and refuses to choose when authority
        scores are close or reviewed evidence is insufficient.

        Args:
            variants: Candidate names and the evidence IDs that explicitly support each name.
            research_context: Optional dynasty, date, place, or research-purpose context.
        """
        repository = evidence_repository
        if repository is None:
            from deerflow.persistence import engine as persistence_engine

            session_factory = persistence_engine.get_session_factory()
            if session_factory is None:
                raise ValueError("name authority resolution requires the SQL evidence database")
            repository = SqlEvidenceRepository(session_factory)
        result = await NameAuthorityService(repository).resolve(
            NameAuthorityRequest(
                variants=tuple(variants),
                research_context=research_context,
            )
        )
        return result.model_dump(mode="json")

    return StructuredTool.from_function(
        coroutine=resolve_name_variants,
        name="resolve_name_variants",
        description=resolve_name_variants.__doc__,
        parse_docstring=True,
    )


def build_xingxi_tools(
    search_service: EvidenceSearchService | None = None,
    *,
    mode: str | XingxiMode | None = None,
    hybrid_search_service: HybridSearchService | None = None,
    structured_search_service: StructuredSearchService | None = None,
    graph_repository: KnowledgeGraphRepository | None = None,
) -> list[BaseTool]:
    tools: list[BaseTool] = [
        build_search_sources_tool(
            search_service,
            hybrid_search_service=hybrid_search_service,
            structured_search_service=structured_search_service,
        ),
        build_query_knowledge_graph_tool(graph_repository),
        build_query_timeline_tool(),
        build_query_map_features_tool(),
        build_gloss_ancient_text_tool(),
        build_resolve_name_variants_tool(),
    ]
    if resolve_mode_profile(mode).mode in {XingxiMode.PRO, XingxiMode.ULTRA}:
        tools.append(
            build_compare_sources_tool(
                hybrid_search_service=hybrid_search_service,
                structured_search_service=structured_search_service,
            )
        )
    return tools
