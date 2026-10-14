"""Synthetic model boundary used only by isolated evaluation subprocesses.

This is scripted replay, not a recording of a real model or a quality judge.
Unexpected questions/tool trajectories fail visibly, including swallowed errors.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from app.gateway.evaluations.suites import EvaluationCase

CURRENT_CASE: EvaluationCase | None = None
REPLAY_ERRORS: list[str] = []
BOUND_TOOLS: list[str] = []
FOLLOWUP = "那它的建成年代有明确记载吗？"


class SyntheticReplayModel(BaseChatModel):
    model: str = "xingxi-synthetic-replay-v1"
    _tool_names: list[str] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "xingxi-synthetic-replay"

    def bind_tools(self, tools, **kwargs):
        self._tool_names = [tool.get("name", tool.get("function", {}).get("name", "")) if isinstance(tool, dict) else tool.name for tool in tools]
        BOUND_TOOLS[:] = self._tool_names
        return self

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        if os.environ.get("XINGXI_EVALUATION_CHILD") != "1" or CURRENT_CASE is None:
            raise RuntimeError("Synthetic replay is restricted to the isolated evaluation worker")
        case = CURRENT_CASE
        human_index = next((index for index in range(len(messages) - 1, -1, -1) if isinstance(messages[index], HumanMessage) and not messages[index].additional_kwargs.get("hide_from_ui")), None)
        if human_index is None or not any(prompt in str(messages[human_index].content) for prompt in (case.question, FOLLOWUP)):
            return self._miss("Unexpected replay question")
        after = messages[human_index + 1 :]
        tool_results = [message for message in after if isinstance(message, ToolMessage)]
        if not tool_results:
            if case.scenario == "gloss":
                name, args = "gloss_ancient_text", {"text": "香溪有桥，始建未详。"}
            else:
                name = "search_sources"
                args: dict[str, Any] = {"query": "测试桥" if case.scenario != "refusal" else "虚构古桥测试人物甲"}
                if case.scenario == "scope":
                    args["document_ids"] = ["nonexistent-evaluation-source"]
            if name not in self._tool_names:
                return self._miss(f"Expected tool is unavailable: {name}")
            message = AIMessage(content="", tool_calls=[{"id": f"eval-{case.id}-{human_index}", "name": name, "args": args}])
        else:
            if len(tool_results) != 1 or tool_results[0].name != case.required_tool:
                return self._miss("Unexpected tool trajectory")
            try:
                tool_output = json.loads(str(tool_results[0].content))
            except (ValueError, TypeError):
                return self._miss("Tool output is not the expected JSON contract")
            if tool_results[0].status == "error":
                return self._miss("Tool returned an error")
            if case.scenario == "gloss":
                content = "香溪有桥，始建未详。这里的“未详”表示建成年代尚不明确。"
            elif case.expect_empty_evidence:
                if tool_output.get("evidence_pack", {}).get("items"):
                    return self._miss("Empty-evidence fixture unexpectedly returned evidence")
                content = "暂无明确方志记载。当前合成资料检索未获得可引用证据，无法据此判断历史上是否存在。"
            else:
                if not tool_output.get("evidence_pack", {}).get("items"):
                    return self._miss("Grounded fixture did not return its seeded evidence")
                evidence_id = tool_output["evidence_pack"]["items"][0]["evidence_id"]
                content = f"测试桥位于测试溪，建成年代未详。[citation:1](evidence://{evidence_id})"
                if case.scenario == "forged_citation":
                    content += " 错误引用[citation:2](evidence://evidence-forged)"
            message = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if CURRENT_CASE and CURRENT_CASE.scenario in {"timeout", "cancel"}:
            await asyncio.sleep(300)
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _miss(self, reason: str):
        REPLAY_ERRORS.append(reason)
        raise ValueError(f"Replay fixture mismatch: {reason}")
