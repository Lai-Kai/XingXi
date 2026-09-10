from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wu_culture.filters import StructuredSearchFilters
from wu_culture.models import AuthorizedUse, Citation, SourceLevel, SourceType


class FullTextSearchError(RuntimeError):
    """Base error for release-scoped full-text search."""


class FullTextReleaseNotIndexed(FullTextSearchError):
    """Raised when a release has no complete full-text index."""


class _FullTextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ParsedFullTextQuery(_FullTextModel):
    phrases: tuple[str, ...] = ()
    terms: tuple[str, ...] = ()
    is_natural_language: bool = False

    @property
    def all_terms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.phrases, *self.terms)))


class FullTextSearchRequest(_FullTextModel):
    query: str = Field(min_length=1, max_length=500)
    release_id: str | None = Field(default=None, min_length=1, max_length=255)
    document_ids: tuple[str, ...] | None = Field(default=None, max_length=100)
    source_levels: tuple[SourceLevel, ...] | None = None
    source_types: tuple[SourceType, ...] | None = None
    authorized_use: AuthorizedUse = AuthorizedUse.PUBLIC_QUOTE
    filters: StructuredSearchFilters = Field(default_factory=StructuredSearchFilters)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_filters(self) -> FullTextSearchRequest:
        if self.document_ids and len(self.document_ids) != len(set(self.document_ids)):
            raise ValueError("duplicate document filter")
        if not parse_fulltext_query(self.query).all_terms:
            raise ValueError("query must contain searchable text")
        return self


class FullTextIndexDocument(_FullTextModel):
    id: str = Field(min_length=1, max_length=255)
    release_id: str = Field(min_length=1, max_length=255)
    release_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    document_id: str = Field(min_length=1, max_length=255)
    source_file_id: str = Field(min_length=1, max_length=255)
    chunk_set_id: str = Field(min_length=1, max_length=255)
    chunk_id: str = Field(min_length=1, max_length=255)
    document_title: str = Field(min_length=1)
    edition: str | None = None
    source_type: SourceType
    source_level: SourceLevel
    volume: str | None = None
    item: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    raw_text: str = Field(min_length=1)
    clean_text: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    indexed_at: datetime

    @property
    def headings(self) -> str:
        return " ".join(value for value in (self.volume, self.item) if value)


class FullTextSearchHit(_FullTextModel):
    release_id: str
    chunk_id: str
    score: float = Field(ge=0)
    matched_terms: tuple[str, ...]
    snippet: str
    citation: Citation


class FullTextSearchResponse(_FullTextModel):
    query: str
    release_id: str
    release_version: str
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    hits: tuple[FullTextSearchHit, ...]


class FullTextIndexResult(_FullTextModel):
    release_id: str
    release_version: str
    indexed_chunks: int = Field(ge=0)
    indexed_at: datetime


class FullTextRepository(Protocol):
    async def resolve_release_id(self, release_id: str | None) -> str: ...

    async def rebuild_release(self, release_id: str, *, indexed_at: datetime) -> FullTextIndexResult: ...

    async def search(self, request: FullTextSearchRequest) -> FullTextSearchResponse: ...


_QUOTED = re.compile(r'["“”]([^"“”]+)["“”]')
_TERM = re.compile(r"[0-9A-Za-z]+|[\u3400-\u9fff]+")
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")

# These words describe the question rather than the historical object. They
# are removed only when one of the explicit question markers is present, so a
# short proper noun such as "何曾" remains an exact phrase.
_QUESTION_MARKERS = (
    "请问",
    "请",
    "介绍",
    "查询",
    "查找",
    "搜索",
    "什么",
    "哪里",
    "在哪",
    "位于",
    "是否",
    "有没有",
    "有无",
    "如何",
    "为什么",
    "为何",
    "哪些",
    "哪个",
    "何时",
    "何地",
    "何人",
    "关系",
    "吗",
    "呢",
)
_QUESTION_STOPWORDS = tuple(
    sorted(
        {
            *_QUESTION_MARKERS,
            "一下",
            "告诉",
            "说明",
            "描述",
            "关于",
            "帮我",
            "的",
            "了",
            "和",
            "与",
            "及",
            "在",
            "是",
            "有",
        },
        key=len,
        reverse=True,
    )
)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def build_keyword_retry_query(query: str) -> str | None:
    """Suggest a core-subject query after an empty agent search.

    Only remove standalone question wording, retaining at least two subject
    terms. Literal quotations and the exact full-text API remain unchanged.
    """
    if any(quote in query for quote in ('"', "'", "“", "”", "‘", "’")):
        return None
    wording = {"历史联系", "歷史聯繫", "历史关系", "歷史關係", "相关记载", "相關記載"}
    terms = query.split()
    subjects = [term for term in terms if term not in wording]
    if len(subjects) < 2 or len(subjects) == len(terms):
        return None
    return " ".join(subjects)


def parse_fulltext_query(query: str) -> ParsedFullTextQuery:
    normalized = unicodedata.normalize("NFKC", query).strip()
    phrases = tuple(dict.fromkeys(_normalize(match) for match in _QUOTED.findall(normalized) if _normalize(match)))
    remainder = _QUOTED.sub(" ", normalized)
    natural_language = any(marker in remainder for marker in _QUESTION_MARKERS)
    raw_terms = tuple(dict.fromkeys(_normalize(match.group(0)) for match in _TERM.finditer(remainder) if _normalize(match.group(0))))
    if natural_language:
        cleaned_remainder = remainder
        for stopword in _QUESTION_STOPWORDS:
            cleaned_remainder = cleaned_remainder.replace(stopword, " ")
        terms = tuple(
            dict.fromkeys(fragment for match in _TERM.finditer(cleaned_remainder) for run in _CJK_RUN.findall(_normalize(match.group(0))) for fragment in (run[index : index + 2] for index in range(max(1, len(run) - 1))) if fragment)
        )
        # Preserve Latin and digit tokens, which do not benefit from CJK
        # bigrams and are still useful in mixed-language source queries.
        terms = tuple(dict.fromkeys((*terms, *(term for term in raw_terms if not _CJK_RUN.fullmatch(term)))))
    else:
        terms = raw_terms
    if not phrases and not natural_language and len(terms) == 1 and _normalize(normalized) == terms[0]:
        return ParsedFullTextQuery(phrases=terms)
    return ParsedFullTextQuery(
        phrases=phrases[:8],
        terms=terms[:16],
        is_natural_language=natural_language,
    )


def score_fulltext_match(*, title: str, headings: str, body: str, phrases: tuple[str, ...], terms: tuple[str, ...]) -> float:
    normalized_title = _normalize(title)
    normalized_headings = _normalize(headings)
    normalized_body = _normalize(body)
    score = 0.0
    for value in phrases:
        term = _normalize(value)
        score += 12.0 if term in normalized_title else 0.0
        score += 7.0 if term in normalized_headings else 0.0
        score += min(normalized_body.count(term), 3) * 3.0
    for value in terms:
        term = _normalize(value)
        score += 8.0 if term in normalized_title else 0.0
        score += 5.0 if term in normalized_headings else 0.0
        score += min(normalized_body.count(term), 3) * 1.5
    return round(score, 6)


def build_highlighted_snippet(text: str, terms: tuple[str, ...], *, max_characters: int = 160) -> str:
    if not text:
        return ""
    matches = [(text.casefold().find(term.casefold()), term) for term in terms if term]
    starts = [start for start, _ in matches if start >= 0]
    anchor = min(starts) if starts else 0
    start = max(0, anchor - max_characters // 3)
    end = min(len(text), start + max_characters)
    start = max(0, end - max_characters)
    snippet = text[start:end]
    ordered_terms = sorted(dict.fromkeys(terms), key=len, reverse=True)
    for term in ordered_terms:
        snippet = re.sub(re.escape(term), lambda match: f"【{match.group(0)}】", snippet, flags=re.IGNORECASE)
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(text):
        snippet = f"{snippet}…"
    return snippet
