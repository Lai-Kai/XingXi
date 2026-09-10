from __future__ import annotations

from wu_culture.compare import CompareSourcesRequest, compare_sources
from wu_culture.evidence_pack import EvidencePack, EvidencePackItem, EvidencePackStatus
from wu_culture.models import ReviewStatus, SourceLevel


def _item(evidence_id: str, document_id: str, title: str, quote: str, rank: int) -> EvidencePackItem:
    return EvidencePackItem(
        rank=rank,
        evidence_id=evidence_id,
        chunk_id=f"chunk-{evidence_id}",
        document_id=document_id,
        document_title=title,
        edition="民国铅印本",
        volume="卷一",
        section="桥梁",
        page_start=10 + rank,
        page_end=10 + rank,
        quote=quote,
        quote_provenance="verbatim",
        quote_truncated=False,
        original_quote_chars=len(quote),
        original_quote_sha256="c" * 64,
        source_level=SourceLevel.A,
        review_status=ReviewStatus.REVIEWED,
    )


def test_two_gazetteers_topic_comparison() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=200,
        input_count=2,
        deduplicated_count=0,
        omitted_count=0,
        document_count=2,
        items=(
            _item("e1", "doc-a", "《木渎小志》", "香溪有普济桥，石梁三孔。", 1),
            _item("e2", "doc-b", "《木渎镇志》", "香溪有普济桥，石梁五孔。", 2),
        ),
    )
    result = compare_sources(CompareSourcesRequest(topic="香溪普济桥"), pack=pack)

    assert result.status == "ready"
    assert len(result.columns) == 2
    assert result.columns[0].quote == "香溪有普济桥，石梁三孔。"
    assert result.pair_diffs
    assert result.pair_diffs[0].diff_snippets
    assert result.export["columns"]


def test_single_document_status() -> None:
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=100,
        input_count=1,
        deduplicated_count=0,
        omitted_count=0,
        document_count=1,
        items=(_item("e1", "doc-a", "《木渎小志》", "香溪有普济桥。", 1),),
    )
    result = compare_sources(CompareSourcesRequest(topic="香溪桥"), pack=pack)
    assert result.status == "single_source"
    assert "第二份" in result.open_questions[0]


def test_empty_and_long_quote_clipping() -> None:
    empty = compare_sources(CompareSourcesRequest(topic="无主题"), pack=None, hits=[])
    assert empty.status == "empty"

    long_quote = "木渎" * 600
    pack = EvidencePack(
        release_id="release-1",
        status=EvidencePackStatus.READY,
        token_budget=4000,
        used_tokens=100,
        input_count=2,
        deduplicated_count=0,
        omitted_count=0,
        document_count=2,
        items=(
            _item("e1", "doc-a", "《木渎小志》", long_quote, 1),
            _item("e2", "doc-b", "《木渎镇志》", long_quote + "桥", 2),
        ),
    )
    result = compare_sources(
        CompareSourcesRequest(topic="木渎", max_quote_chars=120),
        pack=pack,
    )
    assert result.status == "truncated"
    assert all(len(col.quote) <= 120 for col in result.columns)
    assert all(col.quote_truncated for col in result.columns)
