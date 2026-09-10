from __future__ import annotations

import re
from collections.abc import Sequence

from diff_match_patch import diff_match_patch

from wu_culture.evidence_pack import EvidencePack, EvidencePackItem
from wu_culture.hybrid import HybridSearchHit

from .models import (
    ComparePairDiff,
    CompareSourcesRequest,
    CompareSourcesResult,
    SourceColumn,
)


def _level(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _clip_quote(quote: str, max_chars: int) -> tuple[str, bool]:
    if len(quote) <= max_chars:
        return quote, False
    return quote[: max_chars - 1].rstrip() + "…", True


def _column_from_item(item: EvidencePackItem, max_quote_chars: int) -> SourceColumn:
    quote, truncated = _clip_quote(item.quote, max_quote_chars)
    return SourceColumn(
        evidence_id=item.evidence_id,
        document_id=item.document_id,
        document_title=item.document_title,
        edition=item.edition,
        volume=item.volume,
        section=item.section,
        page_start=item.page_start,
        page_end=item.page_end,
        source_level=_level(item.source_level),
        review_status=_level(item.review_status),
        quote=quote,
        quote_truncated=truncated or item.quote_truncated,
        original_quote_chars=item.original_quote_chars,
    )


def _column_from_hit(hit: HybridSearchHit, max_quote_chars: int) -> SourceColumn:
    citation = hit.citation
    quote, truncated = _clip_quote(citation.quote, max_quote_chars)
    return SourceColumn(
        evidence_id=citation.evidence_id,
        document_id=citation.document_id,
        document_title=citation.document_title,
        edition=citation.edition,
        volume=citation.volume,
        section=citation.section,
        page_start=citation.page_start,
        page_end=citation.page_end,
        source_level=_level(citation.source_level),
        review_status=_level(citation.review_status),
        quote=quote,
        quote_truncated=truncated,
        original_quote_chars=len(citation.quote),
    )


def _tokens(text: str) -> set[str]:
    return {m.group(0) for m in re.finditer(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", text)}


def _pair_diff(left: SourceColumn, right: SourceColumn) -> ComparePairDiff:
    left_tokens = _tokens(left.quote)
    right_tokens = _tokens(right.quote)
    common = tuple(sorted(left_tokens & right_tokens))[:12]
    only_left = tuple(sorted(left_tokens - right_tokens))[:8]
    only_right = tuple(sorted(right_tokens - left_tokens))[:8]
    differences: list[str] = []
    if only_left:
        differences.append(f"{left.document_title}独有：{'、'.join(only_left)}")
    if only_right:
        differences.append(f"{right.document_title}独有：{'、'.join(only_right)}")
    if left.source_level != right.source_level:
        differences.append(f"来源等级不同：{left.source_level} vs {right.source_level}")

    dmp = diff_match_patch()
    diffs = dmp.diff_main(left.quote, right.quote)
    dmp.diff_cleanupSemantic(diffs)
    snippets: list[str] = []
    for op, data in diffs:
        if not data or data.isspace():
            continue
        if op == dmp.DIFF_INSERT:
            snippets.append(f"+{data[:48]}")
        elif op == dmp.DIFF_DELETE:
            snippets.append(f"-{data[:48]}")
        if len(snippets) >= 6:
            break

    return ComparePairDiff(
        left_evidence_id=left.evidence_id,
        right_evidence_id=right.evidence_id,
        common_points=common,
        differences=tuple(differences),
        diff_snippets=tuple(snippets),
    )


def _open_questions(columns: Sequence[SourceColumn], pair_diffs: Sequence[ComparePairDiff]) -> tuple[str, ...]:
    questions: list[str] = []
    if len(columns) < 2:
        questions.append("是否需要补充第二份独立文献以形成对读？")
    if any(not diff.common_points for diff in pair_diffs):
        questions.append("当前片段共同点很少，是否换卷目或扩大检索？")
    if any(diff.differences for diff in pair_diffs):
        questions.append("差异点是否需要专家校注或原书页码复核？")
    if not questions:
        questions.append("可继续按人物/地点/年代维度细化对读。")
    return tuple(questions)


def compare_sources(
    request: CompareSourcesRequest,
    *,
    pack: EvidencePack | None = None,
    hits: Sequence[HybridSearchHit] | None = None,
) -> CompareSourcesResult:
    """Build a side-by-side comparison without rewriting source quotes."""
    columns: list[SourceColumn] = []
    if pack is not None and pack.items:
        # Prefer one+ items per document, capped.
        per_doc: dict[str, int] = {}
        for item in sorted(pack.items, key=lambda row: row.rank):
            if request.document_ids and item.document_id not in request.document_ids:
                continue
            count = per_doc.get(item.document_id, 0)
            if count >= request.max_items_per_document:
                continue
            per_doc[item.document_id] = count + 1
            columns.append(_column_from_item(item, request.max_quote_chars))
    elif hits:
        per_doc = {}
        for hit in hits:
            citation = hit.citation
            if request.document_ids and citation.document_id not in request.document_ids:
                continue
            count = per_doc.get(citation.document_id, 0)
            if count >= request.max_items_per_document:
                continue
            per_doc[citation.document_id] = count + 1
            columns.append(_column_from_hit(hit, request.max_quote_chars))

    truncated = any(col.quote_truncated for col in columns)
    if not columns:
        status = "empty"
    elif len({col.document_id for col in columns}) < 2:
        status = "single_source"
    elif truncated:
        status = "truncated"
    else:
        status = "ready"

    pair_diffs: list[ComparePairDiff] = []
    for i, left in enumerate(columns):
        for right in columns[i + 1 :]:
            if left.document_id == right.document_id and left.evidence_id == right.evidence_id:
                continue
            pair_diffs.append(_pair_diff(left, right))

    notes = [
        "原文摘录保持 verbatim/截断 verbatim，不对读结果冒充引用原文。",
        "差异与共同点分栏；结论需由研究者或上层回答另行给出。",
    ]
    if request.document_ids:
        notes.append(f"已限定文献：{', '.join(request.document_ids)}")

    export = {
        "topic": request.topic,
        "release_id": request.release_id or (pack.release_id if pack else None),
        "columns": [col.model_dump(mode="json") for col in columns],
        "pair_diffs": [diff.model_dump(mode="json") for diff in pair_diffs],
        "open_questions": list(_open_questions(columns, pair_diffs)),
    }

    return CompareSourcesResult(
        topic=request.topic,
        release_id=request.release_id or (pack.release_id if pack else None),
        status=status,  # type: ignore[arg-type]
        columns=tuple(columns),
        pair_diffs=tuple(pair_diffs),
        open_questions=_open_questions(columns, pair_diffs),
        notes=tuple(notes),
        export=export,
    )
