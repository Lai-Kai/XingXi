from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deerflow.persistence.operations.evaluations import EvaluationRepository


def _migrate(connection) -> None:
    directory = Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations/versions"
    for filename in ["0028_operations_loop.py", "0044_agent_evaluations.py"]:
        spec = importlib.util.spec_from_file_location(filename[:-3], directory / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()


def test_durable_evaluation_idempotency_claim_cancel_and_immutable_results(tmp_path) -> None:
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'evaluations.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(_migrate)
        repo = EvaluationRepository(async_sessionmaker(engine, expire_on_commit=False))
        cases = [{"id": "case-1", "version": 1, "title": "示例", "question": "问题"}]
        first = await repo.create(actor_id="admin", request_key="same", cases=cases, environment={})
        summary = (await repo.list())[0]
        assert summary["id"] == first["id"] and "results" not in summary
        assert (await repo.create(actor_id="admin", request_key="same", cases=cases, environment={}))["id"] == first["id"]
        with pytest.raises(ValueError, match="idempotency"):
            await repo.create(actor_id="admin", request_key="same", cases=[{**cases[0], "question": "different"}], environment={})
        claimed = await repo.claim(owner="worker-1")
        assert claimed["id"] == first["id"]
        assert await repo.claim(owner="worker-2") is None
        assert not await repo.heartbeat(first["id"], owner="worker-2")
        await repo.record_environment(first["id"], environment={"release_id": "synthetic"}, owner="worker-1")
        assert (await repo.get(first["id"]))["environment"]["corpus"]["release_id"] == "synthetic"
        await repo.record_result(first["id"], case_id="case-1", result={"status": "completed", "verdict": "failed", "answer": "original"}, owner="worker-1")
        await repo.record_result(first["id"], case_id="case-1", result={"status": "completed", "verdict": "passed", "answer": "overwrite"}, owner="worker-1")
        await repo.finish(first["id"], owner="worker-1")
        final = await repo.get(first["id"])
        assert final["results"][0]["answer"] == "original"
        assert final["passed"] == 0 and final["total"] == 1
        await repo.add_review(first["id"], case_id="case-1", actor_id="admin", decision="confirmed", note="复核原始失败")
        await repo.add_review(first["id"], case_id="case-1", actor_id="admin", decision="disagreed", note="补充解释")
        assert len((await repo.get(first["id"]))["reviews"]) == 2
        second = await repo.create(actor_id="admin", request_key="other", cases=cases, environment={}, parent_id=first["id"])
        await repo.cancel(second["id"])
        assert (await repo.get(second["id"]))["status"] == "cancelled"
        assert (await repo.get(second["id"]))["passed"] == 0
        await engine.dispose()

    asyncio.run(scenario())


def test_concurrent_claims_have_one_owner_and_manual_reads_remain_compatible(tmp_path):
    async def scenario():
        from sqlalchemy import text

        from app.gateway.routers.operations import EvaluationRun
        from deerflow.persistence.operations.repository import OperationsRepository

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'concurrent.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(_migrate)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        repository = EvaluationRepository(sf)
        await repository.create(actor_id="admin", request_key="one", cases=[{"id": "one"}], environment={})
        claims = await asyncio.gather(repository.claim(owner="a"), repository.claim(owner="b"))
        assert sum(claim is not None for claim in claims) == 1
        async with sf() as session:
            await session.execute(text("INSERT INTO wu_evaluation_runs(id,status,total,passed,pass_rate,created_by,created_at) VALUES ('legacy','completed',1,0,0,'operator','2026-09-26T00:00:00Z')"))
            await session.commit()
        rows = await OperationsRepository(sf).list_evaluation_runs(limit=10)
        assert len(rows) == 1
        assert EvaluationRun.model_validate(rows[0]).id == "legacy"
        await engine.dispose()

    asyncio.run(scenario())


def test_expired_owner_cannot_write_and_recovery_never_claims_it_as_fresh(tmp_path) -> None:
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(_migrate)
        repo = EvaluationRepository(async_sessionmaker(engine, expire_on_commit=False))
        first = await repo.create(actor_id="admin", request_key="one", cases=[{"id": "one"}], environment={})
        past = datetime.now(UTC) - timedelta(minutes=3)
        await repo.claim(owner="lost", now=past)
        assert await repo.claim(owner="new") is None
        assert (await repo.get(first["id"]))["status"] == "error"
        with pytest.raises(ValueError, match="lease"):
            await repo.record_result(first["id"], case_id="one", result={"status": "completed", "verdict": "passed"}, owner="lost")
        await engine.dispose()

    asyncio.run(scenario())
