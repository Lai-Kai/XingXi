from __future__ import annotations

import json

from app.gateway.evaluations.reports import export_report, write_report


def test_reports_escape_untrusted_content_and_keep_failures(tmp_path):
    report = {
        "id": "batch",
        "status": "completed",
        "total": 2,
        "passed": 0,
        "environment": {},
        "results": [
            {
                "case_id": "one",
                "case": {"title": "=HYPERLINK(1)", "question": "<script>alert(1)</script>"},
                "status": "completed",
                "verdict": "failed",
                "answer": "<script>alert(1)</script>",
                "checks": [{"key": "citation", "label": "引用", "status": "failed", "expected": "真实证据", "actual": "不存在"}],
            },
            {"case_id": "two", "case": {"title": "未执行"}, "status": "error", "verdict": None, "error": "missing credentials"},
        ],
    }
    assert "<script>" not in export_report(report, "html")
    assert "'=HYPERLINK" in export_report(report, "csv")
    output = write_report(report, tmp_path)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["files"] and all(item["sha256"] for item in manifest["files"])
    summary = (output / "summary.md").read_text()
    assert "failed" in summary and "missing credentials" in summary
    assert (output / "index.html").is_file()
