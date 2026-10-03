from __future__ import annotations

from app.gateway.routers.operations import build_dashboard_metrics, grade_regression_run


def test_dashboard_metrics_cover_required_non_3d_indicators() -> None:
    metrics = build_dashboard_metrics(
        answer_events=[
            {"citation_count": 2, "is_accurate": True, "refused": False, "refusal_compliant": None},
            {"citation_count": 0, "is_accurate": False, "refused": True, "refusal_compliant": True},
            {"citation_count": 1, "is_accurate": None, "refused": False, "refusal_compliant": None},
        ],
        feedback_ratings=[1, -1, 1],
        unanswered_count=4,
        map_click_count=12,
        correction_count=3,
        hot_entities=[("entity-mudu", "木渎古镇", 7)],
        evaluation_outcomes=[True, False],
    )

    assert metrics.answer_accuracy_rate == 0.5
    assert metrics.citation_rate == 2 / 3
    assert metrics.refusal_compliance_rate == 1.0
    assert metrics.user_satisfaction_rate == 2 / 3
    assert metrics.unanswered_count == 4
    assert metrics.map_point_click_count == 12
    assert metrics.manual_correction_count == 3
    assert metrics.three_dimensional_load_success_rate is None
    assert metrics.hot_entities[0].entity_id == "entity-mudu"


def test_regression_run_is_deterministically_graded() -> None:
    report = grade_regression_run(
        cases=[
            {"id": "answered", "expected_status": "answered", "min_citations": 1, "required_terms": ["木渎"]},
            {"id": "refusal", "expected_status": "refused", "min_citations": 0, "required_terms": []},
        ],
        observations=[
            {"case_id": "answered", "actual_status": "answered", "citation_count": 2, "answer": "木渎相关史料"},
            {"case_id": "refusal", "actual_status": "answered", "citation_count": 0, "answer": "没有资料"},
        ],
    )

    assert report.total == 2
    assert report.passed == 1
    assert report.pass_rate == 0.5
    assert report.results[1].failure_reasons == ("expected status refused, got answered",)


def test_missing_refusal_observation_cannot_pass() -> None:
    report = grade_regression_run(cases=[{"id": "missing", "expected_status": "refused", "min_citations": 0, "required_terms": []}], observations=[])
    assert report.passed == 0
    assert "missing observation" in report.results[0].failure_reasons


def test_offline_regression_does_not_inflate_online_accuracy() -> None:
    metrics = build_dashboard_metrics(answer_events=[{"is_accurate": False}], feedback_ratings=[], unanswered_count=0, map_click_count=0, correction_count=0, hot_entities=[], evaluation_outcomes=[True] * 10)
    assert metrics.answer_accuracy_rate == 0
