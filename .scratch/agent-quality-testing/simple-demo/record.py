"""Record the user's existing answer; no model call or corpus writes."""

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from deerflow.persistence.operations.grading import grade_manual_regression

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = Path(__file__).resolve().parent
DATABASE = ROOT / "backend/.deer-flow/data/deerflow.db"
CASE_ID = "b88af078-b3d9-4f7c-820b-d7a1ba2d89ea"
RELEASE_ID = "release-2c7aafe43b4247fa86ab0d6b951590e7"


def main():
    answer = (DIRECTORY / "answer.txt").read_text().strip()
    with sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        active = connection.execute("SELECT * FROM wu_evaluation_cases WHERE active=1").fetchall()
        assert len(active) == 1 and active[0]["id"] == CASE_ID
        assert active[0]["expected_status"] == "refused" and active[0]["min_citations"] == 0
        assert json.loads(active[0]["required_terms_json"]) == []
        existing = connection.execute(
            "SELECT r.id FROM wu_evaluation_runs r JOIN wu_evaluation_results x ON x.run_id=r.id "
            "WHERE r.created_by='local-demo' AND r.total=1 AND r.release_id=? AND x.case_id=? AND x.answer=?",
            (RELEASE_ID, CASE_ID, answer),
        ).fetchone()
    if existing:
        run_id = existing["id"]
    else:
        with sqlite3.connect(DATABASE, timeout=10) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            assert connection.execute("SELECT id FROM wu_evaluation_cases WHERE active=1").fetchall() == [(CASE_ID,)]
            report = grade_manual_regression(
                cases=[{"id": CASE_ID, "expected_status": "refused", "min_citations": 0, "required_terms": []}],
                observations=[{"case_id": CASE_ID, "actual_status": "refused", "citation_count": 0, "answer": answer}],
            )
            assert report["total"] == report["passed"] == 1
            run_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO wu_evaluation_runs (id,release_id,status,total,passed,pass_rate,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, RELEASE_ID, "completed", report["total"], report["passed"], report["pass_rate"], "local-demo", str(datetime.now(UTC))),
            )
            for result in report["results"]:
                connection.execute(
                    "INSERT INTO wu_evaluation_results (id,run_id,case_id,actual_status,citation_count,answer,passed,failure_reasons_json) VALUES (?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), run_id, result["case_id"], result["actual_status"], result["citation_count"], result["answer"], result["passed"], json.dumps(result["failure_reasons"], ensure_ascii=False)),
                )

    with sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        cases = []
        for row in connection.execute("SELECT * FROM wu_evaluation_cases ORDER BY created_at DESC"):
            case = dict(row)
            case["active"] = bool(case["active"])
            case["required_terms"] = json.loads(case.pop("required_terms_json"))
            cases.append(case)
        runs = []
        for row in connection.execute("SELECT * FROM wu_evaluation_runs ORDER BY created_at DESC LIMIT 6"):
            run = dict(row)
            run["results"] = []
            for result_row in connection.execute("SELECT * FROM wu_evaluation_results WHERE run_id=?", (run["id"],)):
                result = dict(result_row)
                result["passed"] = bool(result["passed"])
                result["failure_reasons"] = json.loads(result.pop("failure_reasons_json"))
                run["results"].append(result)
            runs.append(run)
        assert any(run["id"] == run_id for run in runs)
    (DIRECTORY / "snapshot.json").write_text(json.dumps({"cases": cases, "runs": runs}, ensure_ascii=False, indent=2))
    print(json.dumps({"recorded_run_id": run_id, "total": 1, "passed": 1, "answer_characters": len(answer)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
