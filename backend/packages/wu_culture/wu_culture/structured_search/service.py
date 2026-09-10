from __future__ import annotations

import base64
import hashlib
import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from wu_culture.aliases import AliasExpansionRequest, AliasExpansionResult
from wu_culture.evidence_pack import EvidencePack, EvidencePackAssembler
from wu_culture.filters import StructuredSearchFilters
from wu_culture.hybrid import (
    HybridChannelReport,
    HybridSearchHit,
    HybridSearchRequest,
    HybridSearchService,
    classify_hybrid_evidence,
)
from wu_culture.models import AuthorizedUse, SearchStatus


class StructuredSearchCursorError(ValueError):
    """Raised when a pagination cursor is malformed or belongs to another request."""


class _StructuredModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class StructuredSearchRequest(_StructuredModel):
    query: str = Field(min_length=1, max_length=500)
    release_id: str | None = Field(default=None, min_length=1, max_length=255)
    authorized_use: AuthorizedUse = AuthorizedUse.PUBLIC_QUOTE
    filters: StructuredSearchFilters = Field(default_factory=StructuredSearchFilters)
    page_size: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    candidate_k: int = Field(default=100, ge=1, le=100)
    min_vector_similarity: float = Field(default=0.0, ge=0, le=1)
    max_alias_expansions: int = Field(default=5, ge=1, le=20)

    @property
    def fingerprint(self) -> str:
        payload = {
            "query": self.query,
            "release_id": self.release_id,
            "authorized_use": self.authorized_use.value,
            "filters": self.filters.model_dump(mode="json", exclude_none=True),
            "candidate_k": self.candidate_k,
            "min_vector_similarity": self.min_vector_similarity,
            "max_alias_expansions": self.max_alias_expansions,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class StructuredSearchCursor(_StructuredModel):
    version: int = Field(default=1, ge=1, le=1)
    release_id: str = Field(min_length=1, max_length=255)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    offset: int = Field(ge=0, le=100)


class StructuredSearchResponse(_StructuredModel):
    query: str
    release_id: str
    filters: StructuredSearchFilters
    page_size: int = Field(ge=1, le=50)
    returned_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0, le=100)
    has_more: bool
    next_cursor: str | None = None
    degraded: bool
    channel_reports: tuple[HybridChannelReport, ...]
    evidence_status: SearchStatus
    message: str
    hits: tuple[HybridSearchHit, ...]
    alias_expansion: AliasExpansionResult | None = None
    evidence_pack: EvidencePack | None = None


class AsyncAliasExpander(Protocol):
    async def expand(self, request: AliasExpansionRequest) -> AliasExpansionResult: ...


class StructuredSearchService:
    """Apply the shared filter schema and stable cursor paging to hybrid search."""

    def __init__(self, hybrid: HybridSearchService, alias_expander: AsyncAliasExpander | None = None) -> None:
        self._hybrid = hybrid
        self._alias_expander = alias_expander

    async def search(self, request: StructuredSearchRequest) -> StructuredSearchResponse:
        cursor = decode_search_cursor(request.cursor) if request.cursor is not None else None
        if cursor is not None and cursor.request_fingerprint != request.fingerprint:
            raise StructuredSearchCursorError("cursor belongs to a different query or filter set")
        if cursor is not None and request.release_id is not None and cursor.release_id != request.release_id:
            raise StructuredSearchCursorError("cursor belongs to a different knowledge release")
        release_id = cursor.release_id if cursor is not None else request.release_id
        hybrid = await self._hybrid.search(
            HybridSearchRequest(
                query=request.query,
                release_id=release_id,
                authorized_use=request.authorized_use,
                filters=request.filters,
                top_k=request.candidate_k,
                candidate_k=request.candidate_k,
                min_vector_similarity=request.min_vector_similarity,
            )
        )
        alias_expansion = None
        merged_hits = hybrid.hits
        degraded = hybrid.degraded
        if self._alias_expander is not None:
            alias_expansion = await self._alias_expander.expand(
                AliasExpansionRequest(
                    query=request.query,
                    release_id=hybrid.release_id,
                    dynasties=request.filters.dynasties or (),
                    max_expansions=request.max_alias_expansions,
                )
            )
            if not alias_expansion.requires_disambiguation and alias_expansion.resolved_query is not None and alias_expansion.resolved_query != request.query:
                expanded = await self._hybrid.search(
                    HybridSearchRequest(
                        query=alias_expansion.resolved_query,
                        release_id=hybrid.release_id,
                        authorized_use=request.authorized_use,
                        filters=request.filters,
                        top_k=request.candidate_k,
                        candidate_k=request.candidate_k,
                        min_vector_similarity=request.min_vector_similarity,
                    )
                )
                seen = {hit.chunk_id for hit in expanded.hits}
                merged_hits = (*expanded.hits, *(hit for hit in merged_hits if hit.chunk_id not in seen))[: request.candidate_k]
                degraded = degraded or expanded.degraded
        if cursor is not None and hybrid.release_id != cursor.release_id:
            raise StructuredSearchCursorError("active knowledge release changed; restart pagination")
        offset = cursor.offset if cursor is not None else 0
        if offset > len(merged_hits):
            raise StructuredSearchCursorError("cursor position no longer exists; restart pagination")
        end = min(offset + request.page_size, len(merged_hits))
        hits = merged_hits[offset:end]
        has_more = end < len(merged_hits)
        next_cursor = (
            encode_search_cursor(
                release_id=hybrid.release_id,
                request_fingerprint=request.fingerprint,
                offset=end,
            )
            if has_more
            else None
        )
        evidence_status, message = classify_hybrid_evidence(hits)
        evidence_pack = EvidencePackAssembler().assemble(hits, release_id=hybrid.release_id)
        return StructuredSearchResponse(
            query=request.query,
            release_id=hybrid.release_id,
            filters=request.filters,
            page_size=request.page_size,
            returned_count=len(hits),
            candidate_count=len(merged_hits),
            has_more=has_more,
            next_cursor=next_cursor,
            degraded=degraded,
            channel_reports=hybrid.channel_reports,
            evidence_status=evidence_status,
            message=message,
            hits=hits,
            alias_expansion=alias_expansion,
            evidence_pack=evidence_pack,
        )


def encode_search_cursor(*, release_id: str, request_fingerprint: str, offset: int) -> str:
    payload = StructuredSearchCursor(
        release_id=release_id,
        request_fingerprint=request_fingerprint,
        offset=offset,
    )
    raw = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_search_cursor(cursor: str) -> StructuredSearchCursor:
    try:
        if len(cursor) > 2048:
            raise ValueError("cursor is too long")
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode())
        payload = json.loads(raw.decode())
        return StructuredSearchCursor.model_validate(payload)
    except Exception as exc:
        raise StructuredSearchCursorError("invalid structured-search cursor") from exc
