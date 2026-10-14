from __future__ import annotations

import json
import sys

from testing_report import artifact_counts, run_check, write_summary


def test_report_keeps_command_failure_and_does_not_accept_missing_artifacts(tmp_path):
    failed = run_check("failing", [sys.executable, "-c", "print('real failure'); raise SystemExit(1)"], cwd=tmp_path, output=tmp_path / "failing", required=["results.json"], timeout=10)
    missing = run_check("missing", [sys.executable, "-c", "print('no report')"], cwd=tmp_path, output=tmp_path / "missing", required=["results.json"], timeout=10)
    assert failed["exit_code"] == 1 and failed["status"] == "error"
    assert missing["status"] == "error"
    write_summary(tmp_path, [failed, missing], environment={"git_sha": "test"})
    result = json.loads((tmp_path / "results.json").read_text())
    assert [check["status"] for check in result["checks"]] == ["error", "error"]
    assert "real failure" in (tmp_path / "failing/command.log").read_text()
    assert (tmp_path / "index.html").is_file()


def test_report_redacts_credentials_in_command_log(tmp_path):
    result = run_check("redaction", [sys.executable, "-c", "print('Authorization: Bearer sensitive-token')"], cwd=tmp_path, output=tmp_path / "redaction", required=[], timeout=10)
    assert result["exit_code"] == 0
    assert "sensitive-token" not in (tmp_path / "redaction/command.log").read_text()


def test_junit_counts_keep_collection_errors_and_skips(tmp_path):
    (tmp_path / "junit.xml").write_text("<testsuites><testsuite><testcase/><testcase><failure/></testcase><testcase><error/></testcase><testcase><skipped/></testcase></testsuite></testsuites>")
    assert artifact_counts(tmp_path) == {"total": 4, "failed": 1, "error": 1, "skipped": 1}
