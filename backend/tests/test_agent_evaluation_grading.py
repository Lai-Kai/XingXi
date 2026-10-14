from __future__ import annotations

from app.gateway.evaluations.grading import asserts_nonexistence, grade_attempt
from app.gateway.evaluations.suites import load_suite


def test_missing_observation_and_empty_answer_never_pass_refusal() -> None:
    case = next(case for case in load_suite() if case.scenario == "refusal")
    missing = grade_attempt(case, {"status": "error", "answer": "", "events": []})
    assert missing["verdict"] is None
    assert missing["status"] == "error"
    empty = grade_attempt(case, {"status": "completed", "run_status": "success", "answer": "", "events": []})
    assert empty["verdict"] == "failed"


def test_answer_with_unbacked_citation_fails_even_when_terms_match() -> None:
    case = next(case for case in load_suite() if case.scenario == "grounded")
    result = grade_attempt(
        case,
        {
            "status": "completed",
            "run_status": "success",
            "agent_run_id": "run-1",
            "answer": "测试桥位于测试溪。[citation:1](evidence://forged)",
            "events": [],
            "evidence": [],
            "release_id": "release-1",
            "expected_release_id": "release-1",
        },
    )
    assert result["verdict"] == "failed"
    check = next(check for check in result["checks"] if check["key"] == "citations_valid")
    assert check["status"] == "failed"
    assert "forged" in str(check["actual"])


def test_cancel_scenario_requires_real_interrupted_run() -> None:
    case = next(case for case in load_suite() if case.scenario == "cancel")
    result = grade_attempt(case, {"status": "completed", "run_status": "success", "events": [], "answer": ""})
    assert result["verdict"] == "failed"


def test_suite_has_thirty_versioned_cases_and_six_smoke_scenarios() -> None:
    cases = load_suite()
    assert len(cases) == len({case.id for case in cases}) == 30
    assert {case.scenario for case in load_suite(smoke=True)} == {"grounded", "refusal", "forged_citation", "revoked", "timeout", "cancel"}
    assert all(case.version == 1 and case.mode in {"flash", "pro", "ultra"} for case in cases)


def test_nonexistence_guard_accepts_explicit_uncertainty_but_rejects_assertion():
    assert not asserts_nonexistence("未找到记录，并不等于历史上不存在。")
    assert asserts_nonexistence("这座桥历史上不存在。")
    assert asserts_nonexistence("未查到不等于历史上不存在。但我认为这座桥历史上不存在。")


def test_revocation_leak_and_expanded_tool_access_fail_specific_checks():
    case = next(case for case in load_suite() if case.scenario == "revoked")
    result = grade_attempt(
        case,
        {
            "status": "completed",
            "run_status": "success",
            "agent_run_id": "actual",
            "answer": "暂无明确方志记载",
            "allowed_tools": ["search_sources", "publish_release"],
            "events": [{"type": "tool_call", "name": "search_sources"}],
            "evidence": [{"evidence_id": "leaked", "verified": False}],
            "release_id": "r",
            "expected_release_id": "r",
        },
    )
    failed = {item["key"] for item in result["checks"] if item["status"] == "failed"}
    assert {"empty_evidence", "tool_boundary"} <= failed


def test_broken_cancellation_cannot_pass_an_expected_interruption():
    case = next(case for case in load_suite() if case.scenario == "cancel")
    result = grade_attempt(case, {"status": "completed", "run_status": "interrupted", "agent_run_id": "actual", "cancel_acknowledged": False})
    assert next(item for item in result["checks"] if item["key"] == "cancel_acknowledged")["status"] == "failed"
