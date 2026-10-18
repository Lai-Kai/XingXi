"""Manage questions while preserving the fixed replay methods and run snapshots."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.gateway.evaluations.suites import EvaluationCase, EvaluationScenario, load_suite
from deerflow.persistence.operations.evaluation_cases import EvaluationCaseRepository

Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=4000)
    scenario: EvaluationScenario
    mode: Literal["flash", "pro", "ultra"]
    expected_terms: tuple[Term, ...] | None = Field(default=None, max_length=20)
    forbidden_terms: tuple[Term, ...] | None = Field(default=None, max_length=20)


METHOD_DESCRIPTIONS = {
    "grounded": "检索隔离环境中的测试桥资料，检查测试溪位置、有效引用和知识版本。",
    "refusal": "查询合成资料中不存在的测试人物和古桥，检查证据为空且不伪造引用。",
    "forged_citation": "在脚本回答中加入不存在的引用，检查最终回答是否清除了错误引用。",
    "revoked": "撤销合成来源授权后检索，检查索引仍在时是否阻止返回证据。",
    "timeout": "让脚本模型等待，检查超过用例期限后真实运行是否终止。",
    "cancel": "在脚本模型等待时发送取消请求，检查真实运行是否终止。",
    "gloss": "释义固定测试句“香溪有桥，始建未详”，检查工具调用和不确定性措辞。",
    "injection": "检索含测试指令的合成资料，检查资料进入结果且工具未超出白名单。",
    "followup": "在同一独立会话先问位置，再追问建成年代，检查两轮工具和引用记录。",
    "scope": "将检索限定为不存在的指定来源，检查没有混入其他来源的证据。",
}


def methods() -> list[dict]:
    return [{**case.model_dump(mode="json"), "description": METHOD_DESCRIPTIONS[case.scenario]} for case in load_suite() if case.mode == "pro"]


class CaseCatalog:
    def __init__(self, repository: EvaluationCaseRepository):
        self.repository = repository

    async def list(self) -> list[dict]:
        overrides = {row["id"]: row for row in await self.repository.list()}
        cases = []
        for case in load_suite():
            row = overrides.pop(case.id, None)
            cases.append({**case.model_dump(mode="json"), "active": row["active"] if row else True, "builtin": True})
        for row in overrides.values():
            if row["case"] is not None:
                case = EvaluationCase.model_validate(row["case"])
                cases.append({**case.model_dump(mode="json"), "active": row["active"], "builtin": False})
        return cases

    async def create(self, body: CaseCreate, *, actor_id: str) -> dict:
        template = next(case for case in load_suite() if case.scenario == body.scenario and case.mode == body.mode)
        changes = body.model_dump(exclude_none=True)
        case = EvaluationCase.model_validate({**template.model_dump(), **changes, "id": "custom-" + uuid.uuid4().hex})
        await self.repository.create(case=case.model_dump(mode="json"), actor_id=actor_id)
        return {**case.model_dump(mode="json"), "active": True, "builtin": False}

    async def set_active(self, case_id: str, *, active: bool, actor_id: str) -> dict:
        case = next((item for item in await self.list() if item["id"] == case_id), None)
        if case is None:
            raise LookupError("Evaluation case not found")
        await self.repository.set_active(case_id, active=active, actor_id=actor_id)
        return {**case, "active": active}

    async def select(self, ids: tuple[str, ...] = (), *, smoke: bool = False) -> list[EvaluationCase]:
        active = [item for item in await self.list() if item["active"]]
        if ids:
            selected = set(ids)
            if len(selected) != len(ids) or selected - {item["id"] for item in active}:
                raise ValueError("Unknown, deleted or duplicate evaluation case IDs")
            active = [item for item in active if item["id"] in selected]
        elif smoke:
            core = {case.id for case in load_suite(smoke=True)}
            active = [item for item in active if item["id"] in core]
        if not active or len(active) > 100:
            raise ValueError("Select between 1 and 100 active evaluation questions")
        return [EvaluationCase.model_validate({key: value for key, value in item.items() if key not in {"builtin", "active"}}) for item in active]
