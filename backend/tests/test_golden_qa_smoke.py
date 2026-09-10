from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter
from wu_culture import EvidenceRecord, EvidenceSearchService, InMemoryEvidenceRepository
from wu_culture.qa_loop import run_bridge_qa_loop
from wu_culture.refusal import REFUSAL_CANONICAL_MESSAGE

FIXTURE = Path(__file__).parent / "fixtures" / "wu_culture" / "synthetic_evidence.json"
GOLDEN = Path(__file__).parent / "fixtures" / "eval" / "golden_qa.json"


def _service(records: list[EvidenceRecord] | None = None) -> EvidenceSearchService:
    if records is None:
        records = TypeAdapter(list[EvidenceRecord]).validate_python(json.loads(FIXTURE.read_text(encoding="utf-8")))
    return EvidenceSearchService(InMemoryEvidenceRepository(records))


def test_golden_bridge_question_is_answerable() -> None:
    result = run_bridge_qa_loop(_service(), query="香溪沿岸有哪些古桥？")
    assert result.status == "answered"
    assert result.citation_count >= 1


def test_golden_dataset_cases() -> None:
    dataset = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert dataset["schema_version"] == "golden-qa-v1"
    service = _service()
    for case in dataset["cases"]:
        if case["id"] == "no-evidence-refusal":
            # Empty repository forces refusal path.
            result = run_bridge_qa_loop(_service([]), query=case["query"])
        else:
            result = run_bridge_qa_loop(service, query=case["query"])
        assert result.status == case["expect_status"], case["id"]
        if case.get("min_citations"):
            assert result.citation_count >= case["min_citations"], case["id"]
        for token in case.get("must_include_any", []):
            assert token in result.answer, case["id"]
        for token in case.get("forbid", []):
            assert token not in result.answer.replace("不等于历史上不存在", ""), case["id"]
        if case["expect_status"] == "refused":
            assert REFUSAL_CANONICAL_MESSAGE in result.answer


def test_eval_report_shape() -> None:
    """Stage 67 lightweight report object for CI smoke."""
    service = _service()
    dataset = json.loads(GOLDEN.read_text(encoding="utf-8"))
    rows = []
    for case in dataset["cases"]:
        if case["id"] == "no-evidence-refusal":
            result = run_bridge_qa_loop(_service([]), query=case["query"])
        else:
            result = run_bridge_qa_loop(service, query=case["query"])
        rows.append(
            {
                "id": case["id"],
                "status": result.status,
                "citation_count": result.citation_count,
                "passed": result.status == case["expect_status"],
            }
        )
    report = {
        "schema_version": "eval-report-v1",
        "total": len(rows),
        "passed": sum(1 for row in rows if row["passed"]),
        "cases": rows,
    }
    assert report["total"] == len(dataset["cases"])
    assert report["passed"] == report["total"]
