from __future__ import annotations

import re
from collections.abc import Iterable

from wu_culture.authorization import evaluate_source_access
from wu_culture.extraction import is_non_historical_text
from wu_culture.models import (
    AuthorizedUse,
    Citation,
    EvidenceRecord,
    ReviewStatus,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchStatus,
    SourceLevel,
)
from wu_culture.repositories import AsyncEvidenceRepository, EvidenceRepository

_NON_SEARCH_CHARS = re.compile(r"[^0-9a-z\u3400-\u9fff]+")
_AUTHORITY_WEIGHT = {
    SourceLevel.A: 0.20,
    SourceLevel.B: 0.16,
    SourceLevel.C: 0.12,
    SourceLevel.D: 0.06,
    SourceLevel.E: 0.0,
    SourceLevel.U: 0.0,
}


def _normalize(value: str) -> str:
    return _NON_SEARCH_CHARS.sub("", value.casefold())


def _query_terms(query: str) -> tuple[str, ...]:
    normalized = _normalize(query)
    if len(normalized) <= 2:
        return (normalized,) if normalized else ()
    return tuple(dict.fromkeys(normalized[index : index + 2] for index in range(len(normalized) - 1)))


def _matches_filters(record: EvidenceRecord, request: SearchRequest) -> bool:
    filters = request.filters
    if filters.document_ids and record.document.id not in filters.document_ids:
        return False
    if filters.source_levels and record.document.source_level not in filters.source_levels:
        return False
    if filters.source_types and record.document.source_type not in filters.source_types:
        return False
    if filters.reviewed_only and (record.chunk.review_status != ReviewStatus.REVIEWED or record.evidence.review_status != ReviewStatus.REVIEWED):
        return False
    return record.evidence.review_status != ReviewStatus.REJECTED


def _searchable_text(record: EvidenceRecord) -> str:
    return _normalize(
        " ".join(
            filter(
                None,
                (
                    record.document.title,
                    record.document.edition,
                    record.chunk.volume,
                    record.chunk.section,
                    record.chunk.original_text,
                    record.chunk.normalized_text,
                    record.evidence.quote,
                ),
            )
        )
    )


def _status_for_hits(hits: Iterable[SearchHit]) -> SearchStatus:
    hits = tuple(hits)
    if any(hit.citation.review_status == ReviewStatus.DISPUTED for hit in hits):
        return SearchStatus.CONFLICTING
    if hits and all(hit.citation.source_level in {SourceLevel.D, SourceLevel.E, SourceLevel.U} for hit in hits):
        return SearchStatus.INFERRED
    return SearchStatus.SUPPORTED


def _search_records(records: Iterable[EvidenceRecord], request: SearchRequest) -> SearchResponse:
    terms = _query_terms(request.query)
    scored: list[SearchHit] = []

    for record in records:
        if is_non_historical_text(record.chunk.normalized_text):
            continue
        if not _matches_filters(record, request):
            continue
        searchable = _searchable_text(record)
        matched = [term for term in terms if term and term in searchable]
        minimum_matches = 1 if len(terms) <= 2 else 2
        if len(matched) < minimum_matches:
            continue

        relevance = len(matched) / max(len(terms), 1)
        reviewed_bonus = 0.05 if record.evidence.review_status == ReviewStatus.REVIEWED else 0.0
        score = round(relevance + _AUTHORITY_WEIGHT[record.document.source_level] + reviewed_bonus, 6)
        scored.append(
            SearchHit(
                chunk_id=record.chunk.id,
                score=score,
                matched_terms=matched,
                citation=Citation(
                    evidence_id=record.evidence.id,
                    document_id=record.document.id,
                    document_title=record.document.title,
                    edition=record.document.edition,
                    volume=record.chunk.volume,
                    section=record.chunk.section,
                    page_start=record.chunk.page_start,
                    page_end=record.chunk.page_end,
                    quote=record.evidence.quote,
                    source_level=record.evidence.source_level,
                    review_status=record.evidence.review_status,
                ),
            )
        )

    hits = sorted(
        scored,
        key=lambda item: (-item.score, item.citation.document_id, item.citation.evidence_id),
    )[: request.top_k]
    if not hits:
        return SearchResponse(
            query=request.query,
            status=SearchStatus.INSUFFICIENT,
            hits=[],
            message="暂无明确方志记载",
        )

    status = _status_for_hits(hits)
    messages = {
        SearchStatus.SUPPORTED: "已检索到可引用证据",
        SearchStatus.CONFLICTING: "检索到存在争议的证据，请并列呈现不同记载",
        SearchStatus.INFERRED: "仅检索到低等级来源或推测，不得表述为确定史实",
    }
    return SearchResponse(query=request.query, status=status, hits=hits, message=messages[status])


class EvidenceSearchService:
    def __init__(
        self,
        repository: EvidenceRepository,
        *,
        authorized_use: AuthorizedUse | None = None,
    ) -> None:
        self._repository = repository
        self._authorized_use = authorized_use

    def search(self, request: SearchRequest) -> SearchResponse:
        records = self._repository.iter_evidence()
        if self._authorized_use is not None:
            records = tuple(record for record in records if evaluate_source_access(record.document, use=self._authorized_use).allowed)
        return _search_records(records, request)


class AsyncEvidenceSearchService:
    def __init__(
        self,
        repository: AsyncEvidenceRepository,
        *,
        authorized_use: AuthorizedUse | None = None,
    ) -> None:
        self._repository = repository
        self._authorized_use = authorized_use

    async def search(self, request: SearchRequest) -> SearchResponse:
        records = await self._repository.list_evidence()
        if self._authorized_use is not None:
            records = tuple(record for record in records if evaluate_source_access(record.document, use=self._authorized_use).allowed)
        return _search_records(records, request)
