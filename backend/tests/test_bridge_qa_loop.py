from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from wu_culture import EvidenceRecord, EvidenceSearchService, InMemoryEvidenceRepository
from wu_culture.qa_loop import run_bridge_qa_loop
from wu_culture.refusal import REFUSAL_CANONICAL_MESSAGE

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wu_culture" / "synthetic_evidence.json"


@pytest.fixture
def records() -> list[EvidenceRecord]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return TypeAdapter(list[EvidenceRecord]).validate_python(payload)


def test_normal_bridge_question_returns_two_openable_citations(records: list[EvidenceRecord]) -> None:
    service = EvidenceSearchService(InMemoryEvidenceRepository(records))
    result = run_bridge_qa_loop(service, query="香溪沿岸有哪些古桥？")

    assert result.status == "answered"
    assert result.citation_count >= 2
    assert len(result.open_citations) >= 2
    for citation in result.open_citations:
        assert citation["page_start"] >= 1
        assert citation["href"].startswith("evidence://")
        # Locator consistency with fixture evidence ids.
        matching = next(r for r in records if r.evidence.id == citation["evidence_id"])
        assert citation["chunk_id"] == matching.chunk.id
        assert citation["page_start"] == matching.chunk.page_start
        assert citation["document_title"] == matching.document.title
    assert result.bridge_names
    assert result.uncertainties
    assert result.process_log
    assert "evidence://" in result.answer


def test_paraphrased_query_still_hits_bridges(records: list[EvidenceRecord]) -> None:
    service = EvidenceSearchService(InMemoryEvidenceRepository(records))
    result = run_bridge_qa_loop(service, query="香溪附近古桥有哪些")
    assert result.status == "answered"
    assert result.citation_count >= 1


def test_document_filter_limits_scope(records: list[EvidenceRecord]) -> None:
    service = EvidenceSearchService(InMemoryEvidenceRepository(records))
    only = [records[0].document.id]
    result = run_bridge_qa_loop(service, query="香溪沿岸有哪些古桥？", document_ids=only)
    assert all(item["document_title"] for item in result.open_citations) or result.status == "refused"
    if result.status == "answered":
        assert all(
            next(r for r in records if r.evidence.id == c["evidence_id"]).document.id in only
            for c in result.open_citations
        )


def test_delete_one_evidence_degrades_gracefully(records: list[EvidenceRecord]) -> None:
    reduced = [r for r in records if r.evidence.id != "synthetic-evidence-c-1"]
    service = EvidenceSearchService(InMemoryEvidenceRepository(reduced))
    result = run_bridge_qa_loop(service, query="香溪沿岸有哪些古桥？")
    assert result.status in {"answered", "refused"}
    if result.status == "answered":
        assert all(c["evidence_id"] != "synthetic-evidence-c-1" for c in result.open_citations)


def test_delete_all_evidence_refuses(records: list[EvidenceRecord]) -> None:
    service = EvidenceSearchService(InMemoryEvidenceRepository([]))
    result = run_bridge_qa_loop(service, query="香溪沿岸有哪些古桥？")
    assert result.status == "refused"
    assert REFUSAL_CANONICAL_MESSAGE in result.answer
    assert "历史上不存在" not in result.answer.replace("不等于历史上不存在", "")


def test_process_log_is_traceable(records: list[EvidenceRecord]) -> None:
    service = EvidenceSearchService(InMemoryEvidenceRepository(records))
    result = run_bridge_qa_loop(service)
    joined = " | ".join(result.process_log)
    assert "query=" in joined
    assert "search_status=" in joined
    assert "evidence_pack_status=" in joined
