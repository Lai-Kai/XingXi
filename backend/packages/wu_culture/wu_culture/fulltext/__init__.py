"""Release-scoped Chinese full-text indexing and exact keyword search."""

from .service import (
    FullTextIndexDocument,
    FullTextIndexResult,
    FullTextReleaseNotIndexed,
    FullTextRepository,
    FullTextSearchError,
    FullTextSearchHit,
    FullTextSearchRequest,
    FullTextSearchResponse,
    ParsedFullTextQuery,
    build_highlighted_snippet,
    build_keyword_retry_query,
    parse_fulltext_query,
    score_fulltext_match,
)

__all__ = [
    "FullTextIndexDocument",
    "FullTextIndexResult",
    "FullTextReleaseNotIndexed",
    "FullTextRepository",
    "FullTextSearchError",
    "FullTextSearchHit",
    "FullTextSearchRequest",
    "FullTextSearchResponse",
    "ParsedFullTextQuery",
    "build_highlighted_snippet",
    "build_keyword_retry_query",
    "parse_fulltext_query",
    "score_fulltext_match",
]
