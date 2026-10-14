"""Local entry point using the same durable repository and worker as the UI."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.gateway.evaluations.reports import write_report
from app.gateway.evaluations.service import BACKEND, EvaluationService, environment_snapshot
from app.gateway.evaluations.suites import select_cases
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine
from deerflow.persistence.operations.evaluations import EvaluationRepository


async def execute(*, output: Path, smoke: bool, case_ids: list[str]) -> int:
    cases = select_cases(case_ids, smoke=smoke)
    directory = output.resolve() / f"agent-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    directory.mkdir(parents=True, exist_ok=False)
    # Both the queue and the child Gateway use fresh databases. Local CLI runs
    # never alter production config, knowledge, users or evaluation history.
    control = directory / "control"
    control.mkdir()
    try:
        await init_engine("sqlite", url=f"sqlite+aiosqlite:///{control / 'deerflow.db'}", sqlite_dir=str(control))
        repository = EvaluationRepository(get_session_factory())
        batch = await repository.create(actor_id="local-cli", request_key=str(uuid.uuid4()), cases=[case.model_dump(mode="json") for case in cases], environment=environment_snapshot())
        service = EvaluationService(repository, directory)
        claimed = await repository.claim(owner=service.owner)
        print(f"Agent 评测开始：{len(cases)} 项；记录目录：{directory / batch['id']}", flush=True)
        await service.execute(claimed)
        result = await repository.get(batch["id"])
        print(f"状态：{result['status']}；通过：{result['passed']}/{result['total']}", flush=True)
        print(f"报告：{directory / batch['id'] / 'index.html'}", flush=True)
        return 2 if result["status"] != "completed" else int(result["passed"] != result["total"])
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        write_report(
            {
                "id": directory.name,
                "status": "error",
                "total": len(cases),
                "passed": 0,
                "environment": {"execution_mode": "replay", "error": error},
                "results": [{"case_id": case.id, "case": case.model_dump(mode="json"), "status": "error", "verdict": None, "error": error} for case in cases],
            },
            directory,
        )
        print(f"执行错误：{error}\n报告：{directory / 'index.html'}", flush=True)
        return 2
    finally:
        await close_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Xingxi through an isolated real Gateway with scripted model responses")
    parser.add_argument("--smoke", action="store_true", help="Run six core pro-mode scenarios")
    parser.add_argument("--case", dest="case_ids", action="append", default=[])
    parser.add_argument("--output", type=Path, default=BACKEND.parent / "reports/testing")
    arguments = parser.parse_args()
    try:
        select_cases(arguments.case_ids, smoke=arguments.smoke)
    except ValueError as exc:
        parser.error(str(exc))
    return asyncio.run(execute(output=arguments.output, smoke=arguments.smoke, case_ids=arguments.case_ids))


if __name__ == "__main__":
    raise SystemExit(main())
