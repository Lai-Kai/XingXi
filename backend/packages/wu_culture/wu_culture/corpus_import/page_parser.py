from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .errors import CorpusImportError
from .models import CorpusTextPage
from .page_markers import parse_page_marker


@dataclass(frozen=True)
class _ParsedPage:
    physical_page_number: int
    folio_label: str
    text: str


def parse_paginated_texts(
    *,
    raw_simplified: Iterable[str] | None = None,
    raw_traditional: Iterable[str],
    clean_traditional: Iterable[str],
    clean_simplified: Iterable[str],
) -> tuple[CorpusTextPage, ...]:
    raw_pages = _parse_text_pages(raw_traditional, role="raw_traditional")
    clean_pages = _parse_text_pages(clean_traditional, role="clean_traditional")
    simplified_pages = _parse_text_pages(clean_simplified, role="clean_simplified")
    raw_simplified_pages = _parse_text_pages(raw_simplified, role="raw_simplified") if raw_simplified is not None else simplified_pages
    if not (len(raw_pages) == len(raw_simplified_pages) == len(clean_pages) == len(simplified_pages)):
        raise CorpusImportError("page_alignment_mismatch", "Raw, clean, and simplified texts must contain the same number of pages")

    result: list[CorpusTextPage] = []
    for raw_page, raw_simplified_page, clean_page, simplified_page in zip(raw_pages, raw_simplified_pages, clean_pages, simplified_pages, strict=True):
        locators = {
            (raw_page.physical_page_number, raw_page.folio_label),
            (raw_simplified_page.physical_page_number, raw_simplified_page.folio_label),
            (clean_page.physical_page_number, clean_page.folio_label),
            (simplified_page.physical_page_number, simplified_page.folio_label),
        }
        if len(locators) != 1:
            raise CorpusImportError("page_locator_mismatch", "Raw, clean, and simplified page locators must match")
        result.append(
            CorpusTextPage(
                physical_page_number=clean_page.physical_page_number,
                folio_label=clean_page.folio_label,
                raw_simplified=raw_simplified_page.text,
                raw_traditional=raw_page.text,
                clean_traditional=clean_page.text,
                clean_simplified=simplified_page.text,
            )
        )
    return tuple(result)


def _parse_text_pages(lines: Iterable[str], *, role: str) -> tuple[_ParsedPage, ...]:
    pages: list[_ParsedPage] = []
    page_number: int | None = None
    folio_label: str | None = None
    content: list[str] = []

    def flush() -> None:
        nonlocal content
        if page_number is not None and folio_label is not None:
            pages.append(_ParsedPage(page_number, folio_label, "\n".join(content).rstrip("\n")))
        content = []

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        marker = parse_page_marker(line)
        if marker is not None:
            flush()
            page_number, folio_label = marker
            continue
        if page_number is None:
            if line.strip():
                raise CorpusImportError("text_before_first_page", f"{role} contains text before its first page marker")
            continue
        content.append(line)
    flush()

    if not pages:
        raise CorpusImportError("page_markers_missing", f"{role} contains no page markers")
    for expected_page, page in enumerate(pages, start=1):
        if page.physical_page_number != expected_page:
            raise CorpusImportError("page_sequence_invalid", f"{role} physical page sequence is not continuous")
    return tuple(pages)
