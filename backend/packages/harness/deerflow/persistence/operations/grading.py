"""Pure grading of manual observations, independent of Gateway models."""


def grade_manual_regression(*, cases: list[dict], observations: list[dict]) -> dict:
    by_case = {row["case_id"]: row for row in observations}
    if len(by_case) != len(observations):
        raise ValueError("Duplicate observations are not allowed")
    if set(by_case) - {case["id"] for case in cases}:
        raise ValueError("Observation refers to an unselected case")
    results = []
    for case in cases:
        observed = by_case.get(case["id"], {"actual_status": "refused", "citation_count": 0, "answer": ""})
        reasons = []
        if case["id"] not in by_case:
            reasons.append("missing observation")
        elif not observed.get("answer", "").strip():
            reasons.append("empty answer")
        if observed["actual_status"] != case["expected_status"]:
            reasons.append(f"expected status {case['expected_status']}, got {observed['actual_status']}")
        if observed.get("citation_count", 0) < case.get("min_citations", 0):
            reasons.append(f"expected at least {case['min_citations']} citations")
        missing = [term for term in case.get("required_terms", []) if term not in observed.get("answer", "")]
        if missing:
            reasons.append("missing required terms: " + ", ".join(missing))
        results.append({"case_id": case["id"], "actual_status": observed["actual_status"], "citation_count": observed.get("citation_count", 0), "answer": observed.get("answer", ""), "passed": not reasons, "failure_reasons": reasons})
    passed = sum(item["passed"] for item in results)
    return {"total": len(results), "passed": passed, "pass_rate": passed / len(results) if results else None, "results": results}
