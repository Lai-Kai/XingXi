from __future__ import annotations

import re

from .models import CorpusQualityIssue, CorpusTextPage

_RAW_LINE_PREFIX_B = re.compile(r"^b(?=[\u3400-\u9fff])", re.MULTILINE)


def analyze_page_quality(pages: tuple[CorpusTextPage, ...]) -> tuple[CorpusQualityIssue, ...]:
    issues: list[CorpusQualityIssue] = []
    for page in pages:
        prefix_count = len(_RAW_LINE_PREFIX_B.findall(page.raw_traditional))
        if prefix_count:
            issues.append(
                _issue(
                    page,
                    code="raw_line_prefix_b",
                    field="raw_traditional",
                    count=prefix_count,
                    message="Raw traditional OCR contains a residual line-start b marker",
                )
            )
        if not page.clean_traditional.strip():
            issues.append(
                _issue(
                    page,
                    code="empty_clean_page",
                    field="clean_traditional",
                    count=1,
                    message="Canonical clean traditional page is empty",
                )
            )
        missing_count = page.clean_traditional.count("□")
        if missing_count:
            issues.append(
                _issue(
                    page,
                    code="missing_glyph_placeholder",
                    field="clean_traditional",
                    count=missing_count,
                    message="Clean traditional text contains missing-glyph placeholders",
                )
            )
        for field in ("raw_traditional", "clean_traditional", "clean_simplified"):
            replacement_count = getattr(page, field).count("�")
            if replacement_count:
                issues.append(
                    _issue(
                        page,
                        code="unicode_replacement_character",
                        field=field,
                        count=replacement_count,
                        message="Text contains Unicode replacement characters",
                    )
                )
    return tuple(issues)


def _issue(
    page: CorpusTextPage,
    *,
    code: str,
    field: str,
    count: int,
    message: str,
) -> CorpusQualityIssue:
    return CorpusQualityIssue(
        code=code,
        field=field,
        count=count,
        physical_page_number=page.physical_page_number,
        folio_label=page.folio_label,
        message=message,
    )
