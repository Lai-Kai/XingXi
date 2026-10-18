from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.gateway.evaluations.api import case_repository, repository, router
from deerflow.persistence.operations.evaluation_cases import EvaluationCaseRepository
from deerflow.persistence.operations.evaluations import EvaluationRepository

ROOT = "/api/operations/evaluations"


def migrate(connection):
    directory = Path(__file__).parents[1] / "packages/harness/deerflow/persistence/migrations/versions"
    for filename in ("0028_operations_loop.py", "0044_agent_evaluations.py", "0046_agent_evaluation_cases.py"):
        spec = importlib.util.spec_from_file_location(filename[:-3], directory / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()


async def client_for(tmp_path, role="admin"):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cases.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(migrate)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.state.evaluation_service = object()
    app.include_router(router)
    app.dependency_overrides[repository] = lambda: EvaluationRepository(sf)
    app.dependency_overrides[case_repository] = lambda: EvaluationCaseRepository(sf)

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user = SimpleNamespace(id="operator", system_role=role, business_role="government")
        return await call_next(request)

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return client, engine, sf


def test_custom_question_is_persistent_executable_and_removal_preserves_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr("app.gateway.evaluations.api.environment_snapshot", lambda: {"execution_mode": "replay"})

    async def scenario():
        client, engine, sf = await client_for(tmp_path)
        async with client:
            catalog = (await client.get(ROOT + "/cases")).json()
            assert len(catalog["cases"]) == 30
            assert len(catalog["methods"]) == 10
            assert all(method["description"] for method in catalog["methods"])
            response = await client.post(
                ROOT + "/cases",
                json={
                    "title": "新增位置问题",
                    "question": "测试桥坐落在哪条溪流？",
                    "scenario": "grounded",
                    "mode": "pro",
                    "expected_terms": ["测试溪"],
                    "forbidden_terms": ["不存在的地点"],
                },
            )
            assert response.status_code == 201, response.text
            created = response.json()
            assert created["active"] and not created["builtin"]
            saved = await EvaluationCaseRepository(sf).list()
            assert saved[0]["case"]["question"] == "测试桥坐落在哪条溪流？"
            response = await client.post(ROOT + "/executions", json={"request_key": "custom-run-key", "case_ids": [created["id"]]})
            assert response.status_code == 202, response.text
            batch = response.json()
            assert batch["spec"]["cases"][0]["question"] == created["question"]
            assert batch["spec"]["cases"][0]["required_tool"] == "search_sources"
            assert (await client.delete(ROOT + "/cases/" + created["id"])).status_code == 200
            assert (await client.delete(ROOT + "/cases/" + created["id"])).status_code == 200
            assert len((await client.get(ROOT + "/catalog")).json()["cases"]) == 30
            rejected = await client.post(ROOT + "/executions", json={"request_key": "removed-run-key", "case_ids": [created["id"]]})
            assert rejected.status_code == 422
            assert (await client.get(ROOT + "/executions/" + batch["id"])).json()["spec"] == batch["spec"]
            await client.post(ROOT + "/executions/" + batch["id"] + "/cancel")
            rerun = await client.post(ROOT + "/executions/" + batch["id"] + "/rerun", json={"request_key": "rerun-deleted-key"})
            assert rerun.status_code == 202, rerun.text
            assert rerun.json()["spec"]["cases"] == batch["spec"]["cases"]
            assert (await client.post(ROOT + "/cases/" + created["id"] + "/restore")).status_code == 200
            assert len((await client.get(ROOT + "/catalog")).json()["cases"]) == 31
        await engine.dispose()

    asyncio.run(scenario())


def test_builtin_removal_updates_smoke_and_catalog_counts_and_can_be_restored(tmp_path):
    async def scenario():
        client, engine, _ = await client_for(tmp_path)
        async with client:
            assert (await client.delete(ROOT + "/cases/grounded-pro")).status_code == 200
            catalog = (await client.get(ROOT + "/catalog")).json()
            assert len(catalog["cases"]) == 29 and catalog["core_count"] == 5
            assert (await client.post(ROOT + "/cases/grounded-pro/restore")).status_code == 200
            assert (await client.get(ROOT + "/catalog")).json()["core_count"] == 6
            assert (await client.delete(ROOT + "/cases/unknown")).status_code == 404
        await engine.dispose()

    asyncio.run(scenario())


def test_reader_can_inspect_but_cannot_change_questions(tmp_path):
    async def scenario():
        client, engine, _ = await client_for(tmp_path, "user")
        async with client:
            assert (await client.get(ROOT + "/cases")).status_code == 200
            body = {"title": "题目", "question": "问题", "scenario": "grounded", "mode": "pro"}
            assert (await client.post(ROOT + "/cases", json=body)).status_code == 403
            assert (await client.delete(ROOT + "/cases/grounded-pro")).status_code == 403
            assert (await client.post(ROOT + "/cases/grounded-pro/restore")).status_code == 403
        await engine.dispose()

    asyncio.run(scenario())


def test_case_input_rejects_blank_fields_and_execution_overrides(tmp_path):
    async def scenario():
        client, engine, _ = await client_for(tmp_path)
        async with client:
            valid = {"title": "题目", "question": "问题", "scenario": "grounded", "mode": "pro"}
            for changes in ({"question": "  "}, {"title": " "}, {"scenario": "shell"}, {"required_tool": "publish_release"}, {"execution_mode": "live"}, {"expected_terms": [""]}):
                assert (await client.post(ROOT + "/cases", json={**valid, **changes})).status_code == 422
        await engine.dispose()

    asyncio.run(scenario())
