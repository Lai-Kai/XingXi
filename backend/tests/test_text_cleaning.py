from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError
from wu_culture.cleaning import CleanedPageContent, RawOcrPage, TextCleaningPolicy, clean_ocr_page, clean_ocr_pages


def test_cleaning_preserves_raw_text_and_records_line_break_change():
    raw_text = "木渎\n古镇"
    page = RawOcrPage(
        source_file_id="source-file-1",
        ocr_attempt_id="ocr-source-file-1-p1-a1",
        page_number=1,
        raw_text=raw_text,
    )
    policy = TextCleaningPolicy(rule_version="xingxi-clean-v1", script_conversion="preserve")

    result = clean_ocr_page(page, policy=policy)

    assert result.raw_text == raw_text
    assert result.raw_sha256 == hashlib.sha256(raw_text.encode()).hexdigest()
    assert result.clean_text == "木渎古镇"
    assert result.clean_sha256 == hashlib.sha256("木渎古镇".encode()).hexdigest()
    assert result.rule_version == "xingxi-clean-v1"
    assert result.script_conversion == "preserve"
    assert [change.model_dump() for change in result.changes] == [
        {
            "sequence": 0,
            "rule_id": "join_single_line_break",
            "raw_start": 2,
            "raw_end": 3,
            "clean_start": 2,
            "clean_end": 2,
            "before": "\n",
            "after": "",
        }
    ]


def test_simplified_policy_records_each_script_conversion_without_mutating_raw():
    page = RawOcrPage(
        source_file_id="source-file-1",
        ocr_attempt_id="ocr-source-file-1-p2-a1",
        page_number=2,
        raw_text="後臺",
    )

    result = clean_ocr_page(page, policy=TextCleaningPolicy(rule_version="xingxi-clean-v1", script_conversion="simplified"))

    assert result.raw_text == "後臺"
    assert result.clean_text == "后台"
    assert [(change.rule_id, change.raw_start, change.raw_end, change.before, change.after) for change in result.changes] == [
        ("script_simplified", 0, 1, "後", "后"),
        ("script_simplified", 1, 2, "臺", "台"),
    ]


def test_batch_cleaning_removes_only_repeated_header_and_page_number_footer():
    pages = (
        RawOcrPage(
            source_file_id="source-file-1",
            ocr_attempt_id="ocr-source-file-1-p1-a1",
            page_number=1,
            raw_text="木渎县志 卷一\n第一段\n- 1 -",
        ),
        RawOcrPage(
            source_file_id="source-file-1",
            ocr_attempt_id="ocr-source-file-1-p2-a1",
            page_number=2,
            raw_text="木渎县志 卷一\n第二段\n- 2 -",
        ),
    )

    results = clean_ocr_pages(pages, policy=TextCleaningPolicy(rule_version="xingxi-clean-v1"))

    assert [result.raw_text for result in results] == [page.raw_text for page in pages]
    assert [result.clean_text for result in results] == ["第一段", "第二段"]
    assert [[change.rule_id for change in result.changes] for result in results] == [
        ["remove_repeated_header", "remove_page_number_footer"],
        ["remove_repeated_header", "remove_page_number_footer"],
    ]


def test_explicit_variant_mapping_is_versioned_and_auditable():
    page = RawOcrPage(
        source_file_id="source-file-1",
        ocr_attempt_id="ocr-source-file-1-p3-a1",
        page_number=3,
        raw_text="衞前街",
    )
    policy = TextCleaningPolicy(
        rule_version="mudu-variants-v1",
        variant_map={"衞": "衛"},
    )

    result = clean_ocr_page(page, policy=policy)

    assert result.raw_text == "衞前街"
    assert result.clean_text == "衛前街"
    assert result.rule_version == "mudu-variants-v1"
    assert [(change.rule_id, change.raw_start, change.before, change.after) for change in result.changes] == [("variant_map", 0, "衞", "衛")]


def test_cleaned_content_rejects_raw_or_clean_hash_tampering():
    result = clean_ocr_page(
        RawOcrPage(source_file_id="source-file-1", ocr_attempt_id="ocr-source-file-1-p1-a1", page_number=1, raw_text="原文"),
        policy=TextCleaningPolicy(rule_version="clean-v1"),
    )

    with pytest.raises(ValidationError, match="raw_sha256 does not match raw_text"):
        CleanedPageContent.model_validate({**result.model_dump(), "raw_text": "被篡改"})

    with pytest.raises(ValidationError, match="clean_sha256 does not match clean_text"):
        CleanedPageContent.model_validate({**result.model_dump(), "clean_text": "被篡改"})


def test_line_ending_policy_joins_wrapped_line_but_preserves_paragraph_break():
    page = RawOcrPage(
        source_file_id="source-file-1",
        ocr_attempt_id="ocr-source-file-1-p4-a1",
        page_number=4,
        raw_text="第一行\r\n第二行\r\n\r\n第三段",
    )

    result = clean_ocr_page(page, policy=TextCleaningPolicy(rule_version="clean-v1"))

    assert result.raw_text == page.raw_text
    assert result.clean_text == "第一行第二行\n\n第三段"
    assert [change.rule_id for change in result.changes] == [
        "normalize_line_ending",
        "normalize_line_ending",
        "normalize_line_ending",
        "join_single_line_break",
    ]


def test_structural_heading_line_breaks_are_not_joined_into_body_text():
    page = RawOcrPage(
        source_file_id="source-file-1",
        ocr_attempt_id="ocr-source-file-1-p5-a1",
        page_number=5,
        raw_text="卷一\n目一\n木渎沿河\n而建。",
    )

    result = clean_ocr_page(page, policy=TextCleaningPolicy(rule_version="clean-v1"))

    assert result.clean_text == "卷一\n目一\n木渎沿河而建。"
    assert [change.rule_id for change in result.changes] == ["join_single_line_break"]
