from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError
from wu_culture import (
    EvidenceRecord,
    EvidenceSearchService,
    InMemoryEvidenceRepository,
    SearchFilters,
    SearchRequest,
    SearchStatus,
    SourceLevel,
)

from deerflow.agents.xingxi.tools import build_search_sources_tool

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wu_culture" / "synthetic_evidence.json"


@pytest.fixture
def evidence_records() -> list[EvidenceRecord]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return TypeAdapter(list[EvidenceRecord]).validate_python(payload)


@pytest.fixture
def search_service(evidence_records: list[EvidenceRecord]) -> EvidenceSearchService:
    return EvidenceSearchService(InMemoryEvidenceRepository(evidence_records))


def test_evidence_record_rejects_broken_document_reference(evidence_records: list[EvidenceRecord]):
    payload = evidence_records[0].model_dump(mode="json")
    payload["chunk"]["document_id"] = "wrong-document"

    with pytest.raises(ValidationError, match="chunk.document_id"):
        EvidenceRecord.model_validate(payload)


def test_search_returns_stable_citations_ranked_by_relevance_and_authority(
    search_service: EvidenceSearchService,
):
    response = search_service.search(SearchRequest(query="香溪沿岸有哪些古桥", top_k=2))

    assert response.status == SearchStatus.SUPPORTED
    assert [hit.citation.evidence_id for hit in response.hits] == [
        "synthetic-evidence-c-1",
        "synthetic-evidence-a-1",
    ]
    assert response.hits[0].citation.page_start == 30
    assert response.hits[0].citation.document_title == "《测试桥梁研究》"


def test_search_filters_source_levels(search_service: EvidenceSearchService):
    response = search_service.search(
        SearchRequest(
            query="香溪桥梁",
            filters=SearchFilters(source_levels=[SourceLevel.A]),
        )
    )

    assert [hit.citation.source_level for hit in response.hits] == [SourceLevel.A]


def test_low_grade_sources_are_never_reported_as_confirmed(search_service: EvidenceSearchService):
    response = search_service.search(
        SearchRequest(
            query="丙桥传说",
            filters=SearchFilters(source_levels=[SourceLevel.D]),
        )
    )

    assert response.status == SearchStatus.INFERRED
    assert "不得表述为确定史实" in response.message


def test_missing_evidence_uses_the_product_refusal_contract(search_service: EvidenceSearchService):
    response = search_service.search(SearchRequest(query="完全不存在于测试资料的问题"))

    assert response.status == SearchStatus.INSUFFICIENT
    assert response.hits == []
    assert response.message == "暂无明确方志记载"


def test_search_sources_tool_returns_structured_citations(search_service: EvidenceSearchService):
    search_sources = build_search_sources_tool(search_service)

    result = search_sources.invoke({"query": "香溪桥梁", "source_levels": ["A"], "top_k": 1})

    assert result["status"] == "supported"
    assert result["hits"][0]["citation"]["evidence_id"] == "synthetic-evidence-a-1"
    assert result["hits"][0]["citation"]["page_start"] == 12
    assert result["hits"][0]["chunk_id"] == "synthetic-chunk-a-1"
    assert "quote" not in result["hits"][0]["citation"]
    assert result["evidence_pack"]["schema_version"] == "evidence-pack-v1"
    assert result["evidence_pack"]["items"][0]["chunk_id"] == "synthetic-chunk-a-1"
