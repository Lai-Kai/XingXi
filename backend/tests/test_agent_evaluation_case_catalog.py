"""Pure catalog/rule regressions independent of Gateway process startup."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import ValidationError

from app.gateway.evaluations import replay_model
from app.gateway.evaluations.api import create_case, delete_case, list_cases, restore_case
from app.gateway.evaluations.case_catalog import CaseCatalog, CaseCreate
from app.gateway.evaluations.suites import load_suite


def test_custom_question_inherits_method_and_runs_through_replay(monkeypatch):
    async def scenario():
        repo = AsyncMock()
        repo.list.return_value = []
        catalog = CaseCatalog(repo)
        created = await catalog.create(CaseCreate(title="自定义位置问题", question="测试桥靠近哪条溪流？", scenario="grounded", mode="pro", expected_terms=["测试溪"]), actor_id="admin")
        stored = repo.create.call_args.kwargs["case"]
        repo.list.return_value = [{"id": created["id"], "case": stored, "active": True}]
        assert len(await catalog.select()) == 31
        assert len(await catalog.select(smoke=True)) == 6
        selected = (await catalog.select((created["id"],), smoke=True))[0]
        assert selected.question == "测试桥靠近哪条溪流？"
        assert selected.required_tool == "search_sources"
        assert selected.min_citations == 1
        assert selected.expected_terms == ("测试溪",)
        assert "active" not in selected.model_dump()
        monkeypatch.setenv("XINGXI_EVALUATION_CHILD", "1")
        monkeypatch.setattr(replay_model, "CURRENT_CASE", selected)
        monkeypatch.setattr(replay_model, "BOUND_TOOLS", [])
        model = replay_model.SyntheticReplayModel().bind_tools([{"name": "search_sources"}])
        human = HumanMessage(content=selected.question)
        call = model._generate([human]).generations[0].message
        assert call.tool_calls[0]["name"] == "search_sources"
        tool = ToolMessage(content=json.dumps({"evidence_pack": {"items": [{"evidence_id": "synthetic-evidence"}]}}), name="search_sources", tool_call_id=call.tool_calls[0]["id"])
        answer = model._generate([human, call, tool]).generations[0].message.content
        assert "测试溪" in answer and "evidence://synthetic-evidence" in answer

    asyncio.run(scenario())


@pytest.mark.parametrize("changes", [{"title": " "}, {"question": "\n "}, {"scenario": "shell"}, {"required_tool": "publish_release"}, {"execution_mode": "live"}, {"expected_terms": [""]}, {"forbidden_terms": ["x"] * 21}])
def test_case_input_only_accepts_bounded_declarative_fields(changes):
    with pytest.raises(ValidationError):
        CaseCreate.model_validate({"title": "题目", "question": "问题", "scenario": "grounded", "mode": "pro", **changes})


def test_question_endpoints_enforce_governance_reads_and_admin_mutations():
    async def scenario():
        repo = AsyncMock()
        repo.list.return_value = []
        request = Request({"type": "http", "state": {"user": SimpleNamespace(id="reader", system_role="user", business_role="government")}})
        assert len((await list_cases(request, repo))["cases"]) == 30
        body = CaseCreate(title="题目", question="问题", scenario="grounded", mode="pro")
        for operation in (create_case(body, request, repo), delete_case("grounded-pro", request, repo), restore_case("grounded-pro", request, repo)):
            with pytest.raises(HTTPException) as denied:
                await operation
            assert denied.value.status_code == 403
        repo.create.assert_not_awaited()
        repo.set_active.assert_not_awaited()
        request.state.user.system_role = "admin"
        assert (await delete_case("grounded-pro", request, repo))["active"] is False
        repo.set_active.assert_awaited_once_with("grounded-pro", active=False, actor_id="reader")
        request.state.user = SimpleNamespace(id="visitor", system_role="user", business_role="public")
        with pytest.raises(HTTPException) as denied:
            await list_cases(request, repo)
        assert denied.value.status_code == 403

    asyncio.run(scenario())


def test_catalog_respects_deleted_questions_and_selection_limits():
    async def scenario():
        repo = AsyncMock()
        repo.list.return_value = [{"id": "grounded-pro", "case": None, "active": False}]
        catalog = CaseCatalog(repo)
        assert len(await catalog.select(smoke=True)) == 5
        with pytest.raises(ValueError, match="deleted"):
            await catalog.select(("grounded-pro",))
        with pytest.raises(ValueError, match="duplicate"):
            await catalog.select(("refusal-pro", "refusal-pro"))
        with pytest.raises(LookupError):
            await catalog.set_active("unknown", active=False, actor_id="admin")
        repo.set_active.assert_not_awaited()
        repo.list.return_value = [{"id": case.id, "case": None, "active": False} for case in load_suite()]
        with pytest.raises(ValueError, match="between 1 and 100"):
            await catalog.select()

    asyncio.run(scenario())
